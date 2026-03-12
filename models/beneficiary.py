import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(String(255), nullable=False, index=True)
    full_name      = Column(String(255), nullable=False)
    bank_name      = Column(String(255), nullable=False)
    account_number = Column(String(100), nullable=False)
    swift_bic      = Column(String(11),  nullable=False)
    routing_number = Column(String(50),  nullable=True)
    country_code   = Column(String(2),   nullable=False)
    currency       = Column(String(3),   nullable=False)
    # Cached after first Airwallex registration — avoids re-registering on every payment
    airwallex_beneficiary_id = Column(String(255), nullable=True)

    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    transactions   = relationship("Transaction", back_populates="beneficiary")
