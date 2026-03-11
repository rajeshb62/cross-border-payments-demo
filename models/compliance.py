import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class LRSRecord(Base):
    """Tracks annual LRS usage per user (resets each financial year)."""

    __tablename__ = "lrs_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    financial_year = Column(String(9), nullable=False)  # e.g. "2025-2026"

    utilized_usd = Column(Numeric(18, 4), nullable=False, default=0)
    limit_usd = Column(Numeric(18, 4), nullable=False, default=250_000)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KYCDocument(Base):
    __tablename__ = "kyc_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    document_type = Column(String(50), nullable=False)  # PASSPORT, AADHAAR, PAN, etc.
    document_number = Column(String(100), nullable=False)
    status = Column(Enum(KYCStatus, name="kyc_status", create_type=False,
                        values_callable=lambda x: [e.value for e in x]),
                   nullable=False, default=KYCStatus.PENDING)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TCSRecord(Base):
    """Audit trail for Tax Collected at Source."""

    __tablename__ = "tcs_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)

    purpose_code = Column(String(10), nullable=False)
    tcs_rate = Column(Numeric(5, 4), nullable=False)   # e.g. 0.005, 0.05, 0.20
    taxable_amount_inr = Column(Numeric(18, 4), nullable=False)
    tcs_amount_inr = Column(Numeric(18, 4), nullable=False)

    financial_year = Column(String(9), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
