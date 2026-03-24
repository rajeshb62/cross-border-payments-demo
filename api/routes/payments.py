import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.merchant import SettlementCurrency
from models.transaction import TransactionStatus, PaymentMethod
from services import payment_service

router = APIRouter()


class PayerInfo(BaseModel):
    upi_id: Optional[str] = None
    bank: Optional[str] = None


class PaymentInitiate(BaseModel):
    merchant_id: uuid.UUID
    inr_amount: Decimal
    payment_method: PaymentMethod
    purpose_code: str
    payer_info: PayerInfo = PayerInfo()


class TransactionOut(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    virtual_account_id: uuid.UUID
    payment_method: PaymentMethod
    inr_amount: Decimal
    fx_rate: Optional[Decimal] = None
    settlement_currency: SettlementCurrency
    settlement_amount: Optional[Decimal] = None
    fee_inr: Optional[Decimal] = None
    tcs_applicable: bool
    tcs_rate: Decimal
    purpose_code: str
    status: TransactionStatus
    payer_upi_id: Optional[str] = None
    payer_bank: Optional[str] = None

    model_config = {"from_attributes": True}


@router.post("", response_model=TransactionOut, status_code=201)
async def initiate_payment(
    body: PaymentInitiate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    tx = await payment_service.initiate_payment(
        merchant_id=body.merchant_id,
        inr_amount=body.inr_amount,
        payment_method=body.payment_method.value,
        purpose_code=body.purpose_code,
        payer_info=body.payer_info.model_dump(),
        db=db,
    )
    # Trigger Celery pipeline asynchronously
    from workers.payment_worker import process_payment_pipeline
    background_tasks.add_task(process_payment_pipeline.delay, str(tx.id))
    return tx


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_payment(transaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await payment_service.get_transaction(transaction_id, db)


@router.get("/merchant/{merchant_id}", response_model=list[TransactionOut])
async def list_merchant_payments(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await payment_service.list_merchant_transactions(merchant_id, db)
