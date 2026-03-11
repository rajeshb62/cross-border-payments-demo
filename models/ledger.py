import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class AccountType(str, enum.Enum):
    CUSTOMER_INR = "customer_inr"
    FX_ACCOUNT = "fx_account"
    CUSTOMER_USD = "customer_usd"
    FEE = "fee"
    TCS = "tcs"


class EntryType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True)

    account_type = Column(Enum(AccountType, name="account_type", create_type=False,
                              values_callable=lambda x: [e.value for e in x]), nullable=False)
    entry_type = Column(Enum(EntryType, name="entry_type", create_type=False,
                             values_callable=lambda x: [e.value for e in x]), nullable=False)
    currency = Column(String(3), nullable=False)  # INR or USD
    amount = Column(Numeric(18, 4), nullable=False)

    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transaction = relationship("Transaction", back_populates="ledger_entries")
