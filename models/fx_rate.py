import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    currency_pair: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # e.g. "INR_USD"
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
