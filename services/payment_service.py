# DEMO SIMPLIFICATION: INR collection is simulated (no real UPI/NetBanking integration).
#   Payment status is moved to inr_collected immediately with no actual bank debit.
# PRODUCTION TODO: Integrate with a payment aggregator (e.g. Razorpay, PayU, Cashfree)
#   to generate a real payment link/QR, receive webhook confirmation, and reconcile
#   against the virtual account. Implement idempotency keys for retries.

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import TransactionNotFoundError, InvalidTransactionStateError
from models.merchant import Merchant, VirtualAccount, SettlementCurrency
from models.transaction import Transaction, TransactionStatus, PaymentMethod


# TCS purpose code rules (demo subset — FEMA guidelines)
TCS_RULES = {
    "P0802": {"rate": Decimal("0"), "applicable": False},   # Software/IT services export — 0%
    "P1007": {"rate": Decimal("0.005"), "applicable": True}, # Education-related — 0.5%
}
DEFAULT_TCS = {"rate": Decimal("0"), "applicable": False}


def compute_tcs(purpose_code: str, inr_amount: Decimal) -> tuple[bool, Decimal, Decimal]:
    """
    Returns (tcs_applicable, tcs_rate, tcs_amount_inr).
    P0802 → 0%; P1007 → 0.5%; others → 0% below ₹7L, 20% above.
    """
    rule = TCS_RULES.get(purpose_code)
    if rule:
        tcs_amount = (inr_amount * rule["rate"]).quantize(Decimal("0.01"))
        return rule["applicable"], rule["rate"], tcs_amount

    # Default FEMA rule for other purpose codes
    threshold = Decimal("700000")
    if inr_amount <= threshold:
        return False, Decimal("0"), Decimal("0")
    else:
        rate = Decimal("0.20")
        tcs_amount = ((inr_amount - threshold) * rate).quantize(Decimal("0.01"))
        return True, rate, tcs_amount


async def initiate_payment(
    merchant_id: uuid.UUID,
    inr_amount: Decimal,
    payment_method: str,
    purpose_code: str,
    payer_info: dict,
    db: AsyncSession,
) -> Transaction:
    """Create a Transaction in status=initiated and return it."""
    # Resolve virtual account for this merchant
    result = await db.execute(
        select(VirtualAccount)
        .where(VirtualAccount.merchant_id == merchant_id)
        .where(VirtualAccount.is_active == True)
        .limit(1)
    )
    virtual_account = result.scalar_one_or_none()
    if not virtual_account:
        raise InvalidTransactionStateError(f"No active virtual account for merchant {merchant_id}")

    # Resolve settlement currency from merchant
    merchant_result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        raise InvalidTransactionStateError(f"Merchant {merchant_id} not found")

    tcs_applicable, tcs_rate, _ = compute_tcs(purpose_code, inr_amount)

    fee_inr = (inr_amount * Decimal(str(settings.PLATFORM_FEE_RATE))).quantize(Decimal("0.01"))

    tx = Transaction(
        merchant_id=merchant_id,
        virtual_account_id=virtual_account.id,
        payment_method=PaymentMethod(payment_method),
        inr_amount=inr_amount,
        settlement_currency=merchant.settlement_currency,
        fee_inr=fee_inr,
        tcs_applicable=tcs_applicable,
        tcs_rate=tcs_rate,
        purpose_code=purpose_code,
        status=TransactionStatus.initiated,
        payer_upi_id=payer_info.get("upi_id"),
        payer_bank=payer_info.get("bank"),
    )
    db.add(tx)
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
