import uuid
from datetime import datetime
from decimal import Decimal
import enum

from sqlalchemy import String, Enum as SAEnum, Numeric, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.merchant import SettlementCurrency


class PaymentMethod(str, enum.Enum):
    upi = "upi"
    netbanking = "netbanking"
    card = "card"


class TransactionStatus(str, enum.Enum):
    initiated = "initiated"
    inr_collected = "inr_collected"
    fx_converted = "fx_converted"
    settled = "settled"
    failed = "failed"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    virtual_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_accounts.id"), nullable=False
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method_enum"), nullable=False
    )
    inr_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=True)
    settlement_currency: Mapped[SettlementCurrency] = mapped_column(
        SAEnum(SettlementCurrency, name="settlement_currency_enum"), nullable=False
    )
    settlement_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    fee_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=True)
    tcs_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tcs_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0"))
    purpose_code: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status_enum"),
        nullable=False,
        default=TransactionStatus.initiated,
    )
    payer_upi_id: Mapped[str] = mapped_column(String(100), nullable=True)
    payer_bank: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    merchant = relationship("Merchant", back_populates="transactions")
    virtual_account = relationship("VirtualAccount")
    reconciliation_logs = relationship("ReconciliationLog", back_populates="transaction", lazy="selectin")
