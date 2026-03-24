import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services import fx_service

router = APIRouter()


class FxRateOut(BaseModel):
    id: uuid.UUID
    currency_pair: str
    rate: Decimal
    fetched_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[FxRateOut])
async def get_fx_rates(db: AsyncSession = Depends(get_db)):
    """Return current cached INR→X rates for all 7 settlement currencies."""
    return await fx_service.get_all_cached_rates(db)
