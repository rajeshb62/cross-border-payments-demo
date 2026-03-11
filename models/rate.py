import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class FXRate(Base):
    """Historical rate snapshots (source of truth for audit)."""

    __tablename__ = "fx_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate = Column(Numeric(10, 6), nullable=False)        # units of from_currency per to_currency
    source = Column(String(50), nullable=False, default="wise_stub")
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class RateLock(Base):
    """Per-transaction rate lock — backed by both Redis TTL and DB row."""

    __tablename__ = "rate_locks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String(255), nullable=False, unique=True, index=True)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    locked_rate = Column(Numeric(10, 6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
