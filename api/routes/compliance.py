from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.compliance import LRSRecord
from services.compliance import (
    _current_financial_year,
    calculate_tcs,
    validate_purpose_code,
)

router = APIRouter()


class LRSStatusResponse(BaseModel):
    user_id: str
    financial_year: str
    utilized_usd: str
    limit_usd: str
    remaining_usd: str


class TCSCalculationResponse(BaseModel):
    amount_inr: str
    purpose_code: str
    purpose_description: str
    is_education_loan: bool
    tcs_rate: str
    tcs_amount_inr: str


@router.get("/lrs/{user_id}", response_model=LRSStatusResponse)
async def get_lrs_status(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    fy = _current_financial_year()
    result = await db.execute(
        select(LRSRecord).where(
            LRSRecord.user_id == user_id,
            LRSRecord.financial_year == fy,
        )
    )
    record = result.scalar_one_or_none()
    utilized = Decimal(str(record.utilized_usd)) if record else Decimal("0")
    limit = Decimal(str(record.limit_usd)) if record else Decimal("250000")
    return LRSStatusResponse(
        user_id=user_id,
        financial_year=fy,
        utilized_usd=str(utilized),
        limit_usd=str(limit),
        remaining_usd=str(limit - utilized),
    )


@router.get("/tcs/calculate", response_model=TCSCalculationResponse)
async def calculate_tcs_endpoint(
    amount_inr: Decimal = Query(gt=0),
    purpose_code: str = Query(),
    is_education_loan: bool = Query(default=False),
) -> Any:
    description = validate_purpose_code(purpose_code)
    tcs_rate, tcs_amount = calculate_tcs(amount_inr, purpose_code, is_education_loan)
    return TCSCalculationResponse(
        amount_inr=str(amount_inr),
        purpose_code=purpose_code,
        purpose_description=description,
        is_education_loan=is_education_loan,
        tcs_rate=str(tcs_rate),
        tcs_amount_inr=str(tcs_amount),
    )
