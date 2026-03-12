import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class TransactionStatus(str, enum.Enum):
    INITIATED = "initiated"
    RATE_LOCKED = "rate_locked"
    COMPLIANCE_CHECK = "compliance_check"
    FUNDS_DEBITED = "funds_debited"
    FX_EXECUTED = "fx_executed"
    FUNDS_CREDITED = "funds_credited"
    PAYOUT_PENDING = "payout_pending"               # payment submitted to Airwallex; awaiting LOCAL rail delivery
    SETTLED = "settled"
    FAILED = "failed"


# Valid forward transitions
ALLOWED_TRANSITIONS: dict[TransactionStatus, set[TransactionStatus]] = {
    TransactionStatus.INITIATED: {TransactionStatus.RATE_LOCKED, TransactionStatus.FAILED},
    TransactionStatus.RATE_LOCKED: {TransactionStatus.COMPLIANCE_CHECK, TransactionStatus.FAILED},
    TransactionStatus.COMPLIANCE_CHECK: {TransactionStatus.FUNDS_DEBITED, TransactionStatus.FAILED},
    TransactionStatus.FUNDS_DEBITED: {TransactionStatus.FX_EXECUTED, TransactionStatus.FAILED},
    TransactionStatus.FX_EXECUTED: {TransactionStatus.FUNDS_CREDITED, TransactionStatus.FAILED},
    TransactionStatus.FUNDS_CREDITED: {TransactionStatus.PAYOUT_PENDING, TransactionStatus.FAILED},
    TransactionStatus.PAYOUT_PENDING: {TransactionStatus.SETTLED, TransactionStatus.FAILED},
    TransactionStatus.SETTLED: set(),
    TransactionStatus.FAILED: set(),
}


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)

    amount_inr = Column(Numeric(18, 4), nullable=False)
    amount_usd = Column(Numeric(18, 4), nullable=True)
    exchange_rate = Column(Numeric(10, 4), nullable=True)

    # FEMA purpose code e.g. P0001, P0002, P0003
    purpose_code = Column(String(10), nullable=False)
    purpose_description = Column(String(255), nullable=True)

    # Education via loan flag — affects TCS rate
    is_education_loan = Column(String(5), nullable=False, default="false")

    status = Column(
        Enum(TransactionStatus, name="transaction_status", create_type=False,
             values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TransactionStatus.INITIATED,
        index=True,
    )

    tcs_amount = Column(Numeric(18, 4), nullable=True)
    rate_lock_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Wire reference from FX provider
    fx_reference_id = Column(String(255), nullable=True)

    # Airwallex payment_id — set when payment is submitted to LOCAL rails
    payout_order_id = Column(String(255), nullable=True, index=True)

    beneficiary_id = Column(UUID(as_uuid=True), ForeignKey("beneficiaries.id"), nullable=True, index=True)

    failure_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    events = relationship("TransactionEvent", back_populates="transaction", order_by="TransactionEvent.created_at")
    ledger_entries = relationship("LedgerEntry", back_populates="transaction")
    beneficiary = relationship("Beneficiary", back_populates="transactions")


class TransactionEvent(Base):
    __tablename__ = "transaction_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True)

    from_status = Column(Enum(TransactionStatus, name="transaction_status", create_type=False,
                             values_callable=lambda x: [e.value for e in x]), nullable=True)
    to_status = Column(Enum(TransactionStatus, name="transaction_status", create_type=False,
                            values_callable=lambda x: [e.value for e in x]), nullable=False)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transaction = relationship("Transaction", back_populates="events")
