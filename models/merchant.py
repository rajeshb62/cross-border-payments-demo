import uuid
from datetime import datetime
import enum

from sqlalchemy import String, Enum as SAEnum, JSON, DateTime, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class SettlementCurrency(str, enum.Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    SGD = "SGD"
    AED = "AED"
    HKD = "HKD"
    CNH = "CNH"


class MerchantStatus(str, enum.Enum):
    pending_kyc = "pending_kyc"
    active = "active"
    suspended = "suspended"


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    country: Mapped[str] = mapped_column(String(10), nullable=False)
    settlement_currency: Mapped[SettlementCurrency] = mapped_column(
        SAEnum(SettlementCurrency, name="settlement_currency_enum"), nullable=False
    )
    settlement_account_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[MerchantStatus] = mapped_column(
        SAEnum(MerchantStatus, name="merchant_status_enum"),
        nullable=False,
        default=MerchantStatus.pending_kyc,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    virtual_accounts = relationship("VirtualAccount", back_populates="merchant", lazy="selectin")
    transactions = relationship("Transaction", back_populates="merchant", lazy="selectin")


class VirtualAccount(Base):
    __tablename__ = "virtual_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    inr_account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String(20), nullable=False, default="EXIMPE0001")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    merchant = relationship("Merchant", back_populates="virtual_accounts")
