# DEMO SIMPLIFICATION: INR collection is simulated (no real UPI/NetBanking integration).
#   Payment status is moved to inr_collected immediately with no actual bank debit.
# PRODUCTION TODO: Integrate with a payment aggregator (e.g. Razorpay, PayU, Cashfree)
#   to generate a real payment link/QR, receive webhook confirmation, and reconcile
#   against the virtual account. Implement idempotency keys for retries.

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import (
    TransactionNotFoundError,
    InvalidTransactionStateError,
    OGPSPLimitExceededError,
)
from models.merchant import Merchant, VirtualAccount
from models.transaction import Transaction, TransactionStatus, PaymentMethod
from services import fx_service
from services.merchant_service import check_merchant_approved


async def initiate_payment(
    merchant_id: uuid.UUID,
    inr_amount: Decimal,
    payment_method: str,
    purpose_code: str,
    payer_upi_id: str | None,
    payer_bank: str | None,
    db: AsyncSession,
) -> Transaction:
    """Create a Transaction in status=initiated and return it with UPI intent details."""
    # 1. Verify merchant is KYB approved
    merchant = await check_merchant_approved(merchant_id, db)

    # 2. Resolve virtual account for this merchant
    result = await db.execute(
        select(VirtualAccount)
        .where(VirtualAccount.merchant_id == merchant_id)
        .where(VirtualAccount.is_active == True)
        .limit(1)
    )
    virtual_account = result.scalar_one_or_none()
    if not virtual_account:
        raise InvalidTransactionStateError(f"No active virtual account for merchant {merchant_id}")

    # 3. Compute USD equivalent for OPGSP cap check
    inr_to_usd_rate = await fx_service.get_rate("INR", "USD", db)
    # inr_to_usd_rate is INR per 1 USD; so USD = inr_amount / rate
    usd_equivalent = (inr_amount / inr_to_usd_rate).quantize(Decimal("0.0001"))

    opgsp_cap = Decimal(str(settings.OPGSP_CAP_USD))
    if usd_equivalent > opgsp_cap:
        max_inr = (opgsp_cap * inr_to_usd_rate).quantize(Decimal("0.01"))
        raise OGPSPLimitExceededError(
            f"Amount exceeds OPGSP cap of USD {settings.OPGSP_CAP_USD:.2f} "
            f"(~INR {max_inr}). Requested: USD {usd_equivalent:.2f}"
        )

    # 4. Lock FX rate for settlement currency
    now = datetime.now(timezone.utc)
    locked_rate = await fx_service.get_rate("INR", merchant.settlement_currency.value, db)
    rate_lock_expires = now + timedelta(seconds=settings.FX_RATE_LOCK_TTL_SECONDS)

    # 5. Compute fee
    fee_inr = (inr_amount * Decimal(str(settings.PLATFORM_FEE_RATE))).quantize(Decimal("0.01"))

    # 6. Create the transaction (need ID for UPI VPA generation)
    tx = Transaction(
        merchant_id=merchant_id,
        virtual_account_id=virtual_account.id,
        payment_method=PaymentMethod(payment_method),
        inr_amount=inr_amount,
        settlement_currency=merchant.settlement_currency,
        fee_inr=fee_inr,
        purpose_code=purpose_code,
        status=TransactionStatus.initiated,
        payer_upi_id=payer_upi_id,
        payer_bank=payer_bank,
        usd_equivalent=usd_equivalent,
        opgsp_cap_applied=False,
        fx_rate_locked=locked_rate,
        fx_rate_locked_at=now,
        fx_rate_expires_at=rate_lock_expires,
        merchant_country=merchant.country,
    )
    db.add(tx)
    await db.flush()  # get tx.id

    # 7. Generate UPI intent fields using tx.id
    tx_id_short = str(tx.id)[:8]
    vpa = f"eximpe.{tx_id_short}@icici"
    upi_deep_link = (
        f"upi://pay?pa={vpa}&pn={merchant.name}&am={inr_amount}&cu=INR&tn={tx_id_short}"
    )
    tx.vpa = vpa
    tx.upi_deep_link = upi_deep_link
    tx.upi_qr_payload = upi_deep_link
    tx.payment_expires_at = now + timedelta(minutes=15)
    tx.opgsp_ref = f"OPGSP{str(tx.id).replace('-', '')[:16].upper()}"

    await db.commit()
    await db.refresh(tx)
    return tx


async def simulate_inr_collection(transaction_id: uuid.UUID, db: AsyncSession) -> Transaction:
    """Simulate INR arriving at the virtual account. Moves status to inr_collected."""
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    tx = result.scalar_one_or_none()
    if not tx:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found")
    if tx.status != TransactionStatus.initiated:
        raise InvalidTransactionStateError(
            f"Cannot collect INR for transaction in status {tx.status}"
        )
    tx.status = TransactionStatus.inr_collected
    await db.commit()
    await db.refresh(tx)
    return tx


async def process_upi_webhook(payload: dict, db: AsyncSession) -> Transaction:
    """
    Handle UPI payment webhook from payment aggregator.
    Finds transaction by VPA, updates status based on payment outcome.
    """
    vpa = payload.get("vpa")
    if not vpa:
        raise InvalidTransactionStateError("Webhook payload missing 'vpa' field")

    result = await db.execute(select(Transaction).where(Transaction.vpa == vpa))
    tx = result.scalar_one_or_none()
    if not tx:
        raise TransactionNotFoundError(f"No transaction found for VPA {vpa}")

    allowed_statuses = {TransactionStatus.initiated, TransactionStatus.inr_collected}
    if tx.status not in allowed_statuses:
        raise InvalidTransactionStateError(
            f"Cannot process webhook for transaction in status {tx.status}"
        )

    webhook_status = payload.get("status", "").upper()
    if webhook_status == "SUCCESS":
        tx.upi_ref = payload.get("upi_ref")
        amount_inr = payload.get("amount_inr")
        if amount_inr is not None:
            tx.amount_inr_collected = Decimal(str(amount_inr))
        tx.status = TransactionStatus.upi_confirmed
        await db.commit()
        await db.refresh(tx)

        # Trigger settlement pipeline
        try:
            from workers.payment_worker import process_payment_pipeline
            process_payment_pipeline.delay(str(tx.id))
        except Exception:
            pass  # Don't fail webhook response if Celery is unavailable

    elif webhook_status == "FAILED":
        tx.status = TransactionStatus.failed
        await db.commit()
        await db.refresh(tx)

    return tx


async def get_transaction(transaction_id: uuid.UUID, db: AsyncSession) -> Transaction:
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    tx = result.scalar_one_or_none()
    if not tx:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found")
    return tx


async def list_merchant_transactions(merchant_id: uuid.UUID, db: AsyncSession) -> list[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.merchant_id == merchant_id)
    )
    return list(result.scalars().all())
