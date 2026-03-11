from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.fx_rate import get_live_rate, lock_rate

router = APIRouter()


class QuoteResponse(BaseModel):
    from_currency: str
    to_currency: str
    amount_from: str
    rate: str
    amount_to: str
    lock_ttl_seconds: int
    note: str


@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    from_currency: str = Query(default="INR", alias="from"),
    to_currency: str = Query(default="USD", alias="to"),
    amount: Decimal = Query(gt=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return a live rate quote. Does NOT lock the rate (no transaction_id)."""
    rate = await get_live_rate(from_currency, to_currency)
    amount_to = (amount / rate).quantize(Decimal("0.0001"))
    return QuoteResponse(
        from_currency=from_currency,
        to_currency=to_currency,
        amount_from=str(amount),
        rate=str(rate),
        amount_to=str(amount_to),
        lock_ttl_seconds=90,
        note="Rate is indicative. Locks on transaction creation.",
    )
