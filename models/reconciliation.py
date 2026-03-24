import uuid
from datetime import datetime
from decimal import Decimal
import enum

from sqlalchemy import String, Enum as SAEnum, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class ReconciliationStatus(str, enum.Enum):
    matched = "matched"
    mismatch = "mismatch"
    pending = "pending"


class ReconciliationLog(Base):
    __tablename__ = "reconciliation_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )
    expected_settlement_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    actual_settlement_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[ReconciliationStatus] = mapped_column(
        SAEnum(ReconciliationStatus, name="reconciliation_status_enum"),
        nullable=False,
        default=ReconciliationStatus.pending,
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction = relationship("Transaction", back_populates="reconciliation_logs")
