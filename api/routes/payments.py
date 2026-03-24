import hashlib
import hmac
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from models.merchant import SettlementCurrency
from models.transaction import TransactionStatus, PaymentMethod
from services import payment_service

router = APIRouter()


class PaymentInitiate(BaseModel):
    merchant_id: uuid.UUID
    inr_amount: Decimal
    payment_method: PaymentMethod
    purpose_code: str
    payer_upi_id: Optional[str] = None
    payer_bank: Optional[str] = None


class UPIWebhookPayload(BaseModel):
    txn_id: str
    upi_ref: str
    status: str  # SUCCESS / FAILED / PENDING
    amount_inr: Decimal
    vpa: str
    timestamp: str


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
    purpose_code: str
    status: TransactionStatus
    payer_upi_id: Optional[str] = None
    payer_bank: Optional[str] = None
    # UPI intent
    upi_deep_link: Optional[str] = None
    upi_qr_payload: Optional[str] = None
    vpa: Optional[str] = None
    upi_ref: Optional[str] = None
    payment_expires_at: Optional[datetime] = None
    # OPGSP
    usd_equivalent: Optional[Decimal] = None
    opgsp_cap_applied: Optional[bool] = None
    fx_rate_locked: Optional[Decimal] = None
    fx_rate_expires_at: Optional[datetime] = None
    merchant_country: Optional[str] = None
    opgsp_ref: Optional[str] = None
    # Settlement tracking
    settlement_initiated_at: Optional[datetime] = None
    settlement_completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaymentStatusOut(BaseModel):
    payment_id: uuid.UUID
    status: TransactionStatus
    upi_ref: Optional[str] = None
    settlement_currency: Optional[str] = None
    settlement_amount: Optional[Decimal] = None
    estimated_settlement: str


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
        payer_upi_id=body.payer_upi_id,
        payer_bank=body.payer_bank,
        db=db,
    )
    # Trigger Celery pipeline asynchronously (optional — webhook flow is primary)
    from workers.payment_worker import process_payment_pipeline
    background_tasks.add_task(process_payment_pipeline.delay, str(tx.id))
    return tx


@router.post("/webhook/upi", status_code=200)
async def upi_webhook(
    body: UPIWebhookPayload,
    db: AsyncSession = Depends(get_db),
    x_eximpe_signature: Optional[str] = Header(None),
):
    """
    Receive UPI payment confirmation webhook from payment aggregator.
    Validates HMAC-SHA256 signature from X-EximPe-Signature header.
    """
    # Validate webhook signature
    body_dict = body.model_dump(mode="json")
    # Sort keys for deterministic serialisation
    body_dict_sorted = {k: str(v) if not isinstance(v, str) else v for k, v in sorted(body_dict.items())}
    expected_sig = hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        json.dumps(body_dict, sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()

    if x_eximpe_signature is None or not hmac.compare_digest(x_eximpe_signature, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    await payment_service.process_upi_webhook(body.model_dump(), db)
    return {"received": True}


@router.get("/{payment_id}/status", response_model=PaymentStatusOut)
async def get_payment_status(payment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get lightweight payment status for polling / customer display."""
    tx = await payment_service.get_transaction(payment_id, db)

    settled_statuses = {TransactionStatus.settled, TransactionStatus.fx_converted}
    if tx.status in settled_statuses:
        estimated = "T+2 business days"
    else:
        estimated = "Awaiting UPI confirmation"

    return PaymentStatusOut(
        payment_id=tx.id,
        status=tx.status,
        upi_ref=tx.upi_ref,
        settlement_currency=tx.settlement_currency.value if tx.settlement_currency else None,
        settlement_amount=tx.settlement_amount,
        estimated_settlement=estimated,
    )


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_payment(transaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await payment_service.get_transaction(transaction_id, db)


@router.get("/merchant/{merchant_id}", response_model=list[TransactionOut])
async def list_merchant_payments(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await payment_service.list_merchant_transactions(merchant_id, db)
