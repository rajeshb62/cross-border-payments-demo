from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.beneficiary import Beneficiary
from models.transaction import Transaction
from services import transaction as tx_svc
from workers.tasks import process_transaction

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateTransactionRequest(BaseModel):
    user_id: str
    amount_inr: Decimal = Field(gt=0, description="Amount in INR")
    purpose_code: str = Field(min_length=5, max_length=10)
    is_education_loan: bool = False
    idempotency_key: str | None = None
    beneficiary_id: str | None = None


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    idempotency_key: str
    amount_inr: str
    amount_usd: str | None
    exchange_rate: str | None
    purpose_code: str
    status: str
    tcs_amount: str | None
    fx_reference_id: str | None
    failure_reason: str | None
    beneficiary_id: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_orm(cls, tx: Transaction) -> "TransactionResponse":
        return cls(
            id=str(tx.id),
            user_id=tx.user_id,
            idempotency_key=tx.idempotency_key,
            amount_inr=str(tx.amount_inr),
            amount_usd=str(tx.amount_usd) if tx.amount_usd else None,
            exchange_rate=str(tx.exchange_rate) if tx.exchange_rate else None,
            purpose_code=tx.purpose_code,
            status=tx.status.value,
            tcs_amount=str(tx.tcs_amount) if tx.tcs_amount else None,
            fx_reference_id=tx.fx_reference_id,
            failure_reason=tx.failure_reason,
            beneficiary_id=str(tx.beneficiary_id) if tx.beneficiary_id else None,
            created_at=tx.created_at.isoformat() if tx.created_at else "",
            updated_at=tx.updated_at.isoformat() if tx.updated_at else "",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    body: CreateTransactionRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    idempotency_key = body.idempotency_key or str(uuid.uuid4())

    beneficiary_uuid = None
    if body.beneficiary_id:
        beneficiary_uuid = uuid.UUID(body.beneficiary_id)
        result = await db.execute(
            select(Beneficiary).where(Beneficiary.id == beneficiary_uuid)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Beneficiary not found")

    tx = await tx_svc.create_transaction(
        db=db,
        user_id=body.user_id,
        amount_inr=body.amount_inr,
        purpose_code=body.purpose_code,
        idempotency_key=idempotency_key,
        is_education_loan=body.is_education_loan,
        beneficiary_id=beneficiary_uuid,
    )
    return TransactionResponse.from_orm(tx)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    tx = await tx_svc.get_transaction(db, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionResponse.from_orm(tx)


@router.get("", response_model=list[TransactionResponse])
async def list_transactions(
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> Any:
    txs = await tx_svc.list_transactions(db, user_id=user_id, limit=limit, offset=offset)
    return [TransactionResponse.from_orm(t) for t in txs]


@router.post("/{transaction_id}/execute", response_model=TransactionResponse)
async def execute_transaction(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    tx = await tx_svc.get_transaction(db, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    process_transaction.delay(transaction_id)
    return TransactionResponse.from_orm(tx)
