from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.beneficiary import Beneficiary

router = APIRouter()


class CreateBeneficiaryRequest(BaseModel):
    user_id:        str
    full_name:      str = Field(min_length=1, max_length=255)
    bank_name:      str = Field(min_length=1, max_length=255)
    account_number: str = Field(min_length=1, max_length=100)
    swift_bic:      str = Field(min_length=8, max_length=11)
    routing_number: str | None = None
    country_code:   str = Field(min_length=2, max_length=2)
    currency:       str = Field(min_length=3, max_length=3)


class BeneficiaryResponse(BaseModel):
    id:             str
    user_id:        str
    full_name:      str
    bank_name:      str
    account_number: str
    swift_bic:      str
    routing_number: str | None
    country_code:   str
    currency:       str
    created_at:     str

    @classmethod
    def from_orm(cls, b: Beneficiary) -> "BeneficiaryResponse":
        return cls(
            id=str(b.id),
            user_id=b.user_id,
            full_name=b.full_name,
            bank_name=b.bank_name,
            account_number=b.account_number,
            swift_bic=b.swift_bic,
            routing_number=b.routing_number,
            country_code=b.country_code,
            currency=b.currency,
            created_at=b.created_at.isoformat() if b.created_at else "",
        )


@router.post("", response_model=BeneficiaryResponse, status_code=201)
async def create_beneficiary(
    body: CreateBeneficiaryRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    b = Beneficiary(
        id=uuid.uuid4(),
        user_id=body.user_id,
        full_name=body.full_name,
        bank_name=body.bank_name,
        account_number=body.account_number,
        swift_bic=body.swift_bic.upper(),
        routing_number=body.routing_number,
        country_code=body.country_code.upper(),
        currency=body.currency.upper(),
    )
    db.add(b)
    await db.flush()
    return BeneficiaryResponse.from_orm(b)


@router.get("/{beneficiary_id}", response_model=BeneficiaryResponse)
async def get_beneficiary(
    beneficiary_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(
        select(Beneficiary).where(Beneficiary.id == uuid.UUID(beneficiary_id))
    )
    b = result.scalar_one_or_none()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return BeneficiaryResponse.from_orm(b)


@router.get("", response_model=list[BeneficiaryResponse])
async def list_beneficiaries(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    q = select(Beneficiary).order_by(Beneficiary.created_at.desc())
    if user_id:
        q = q.where(Beneficiary.user_id == user_id)
    result = await db.execute(q)
    return [BeneficiaryResponse.from_orm(b) for b in result.scalars().all()]
