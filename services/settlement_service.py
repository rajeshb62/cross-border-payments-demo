# DEMO SIMPLIFICATION: FX conversion and settlement are simulated in-process.
#   No real SWIFT/SEPA/ACH transfer occurs. Reconciliation variance is a random noise value.
# PRODUCTION TODO: Integrate with a settlement rail provider (e.g. Airwallex, Wise Business,
#   Currencycloud). Implement T+1/T+2 settlement windows, nostro/vostro account management,
#   beneficiary KYC checks, and regulatory reporting (FEMA/RBI).

import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import TransactionNotFoundError, InvalidTransactionStateError
from models.transaction import Transaction, TransactionStatus
from models.reconciliation import ReconciliationLog, ReconciliationStatus
from services import fx_service


async def process_settlement(transaction_id: uuid.UUID, db: AsyncSession) -> Transaction:
    """
    Full settlement pipeline for a transaction in inr_collected or upi_confirmed state:
    1. Determine FX rate (use locked rate if still valid, else fetch fresh)
    2. Deduct 1.5% platform fee from INR amount
    3. Compute settlement amount in merchant's currency
    4. Move status → fx_converted → settled
    5. Log to ReconciliationLog with simulated minor variance
    """
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    tx = result.scalar_one_or_none()
    if not tx:
        raise TransactionNotFoundError(f"Transaction {transaction_id} not found")

    # Accept both inr_collected (direct simulation) and upi_confirmed (webhook flow)
    allowed = {TransactionStatus.inr_collected, TransactionStatus.upi_confirmed}
    if tx.status not in allowed:
        raise InvalidTransactionStateError(
            f"Cannot settle transaction in status {tx.status}"
        )

    now = datetime.now(timezone.utc)
    tx.settlement_initiated_at = now

    # Step 1: Determine FX rate
    # SQLite returns offset-naive datetimes; ensure comparison is apples-to-apples
    expires_at = tx.fx_rate_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if (
        tx.fx_rate_locked is not None
        and expires_at is not None
        and expires_at > now
    ):
        # Use the locked rate
        rate = tx.fx_rate_locked
    else:
        # Lock expired or never set — fetch fresh rate and store as final
        rate, _ = await fx_service.convert(tx.inr_amount, tx.settlement_currency.value, db)
        tx.fx_rate_final = rate

    # Step 2: Compute gross settlement using the chosen rate
    gross_settlement = (tx.inr_amount / rate).quantize(Decimal("0.0001"))

    # Step 3: Deduct fee (fee_inr already computed at initiation; convert to settlement currency)
    fee_in_settlement = (tx.fee_inr / rate).quantize(Decimal("0.0001"))
    net_settlement = gross_settlement - fee_in_settlement

    # Update transaction
    tx.fx_rate = rate
    tx.settlement_amount = net_settlement.quantize(Decimal("0.0001"))
    tx.status = TransactionStatus.fx_converted
    await db.flush()

    tx.status = TransactionStatus.settled
    tx.settlement_completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tx)

    # Step 5: Log reconciliation with simulated variance (±0.1%)
    variance = Decimal(str(random.uniform(-0.001, 0.001)))
    actual_amount = (net_settlement * (1 + variance)).quantize(Decimal("0.0001"))
    is_matched = abs(actual_amount - net_settlement) / net_settlement < Decimal("0.0005")

    recon = ReconciliationLog(
        transaction_id=tx.id,
        expected_settlement_amount=net_settlement,
        actual_settlement_amount=actual_amount,
        status=ReconciliationStatus.matched if is_matched else ReconciliationStatus.mismatch,
    )
    db.add(recon)
    await db.commit()

    return tx
