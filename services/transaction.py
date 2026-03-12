"""Transaction state machine and orchestration."""
from __future__ import annotations

import logging
import uuid as uuid_module
from decimal import Decimal

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import InvalidStateMachineTransitionError
from models.transaction import (
    ALLOWED_TRANSITIONS,
    Transaction,
    TransactionEvent,
    TransactionStatus,
)
from services import compliance as compliance_svc
from services import fx_rate as fx_rate_svc
from services import ledger as ledger_svc
from services import airwallex as airwallex_svc


async def create_transaction(
    db: AsyncSession,
    user_id: str,
    amount_inr: Decimal,
    purpose_code: str,
    idempotency_key: str,
    is_education_loan: bool = False,
    purpose_description: str | None = None,
    beneficiary_id: "uuid_module.UUID | None" = None,
) -> Transaction:
    """Create transaction; return existing on duplicate idempotency_key."""
    desc = compliance_svc.validate_purpose_code(purpose_code)

    tx = Transaction(
        id=uuid_module.uuid4(),
        idempotency_key=idempotency_key,
        user_id=user_id,
        amount_inr=amount_inr,
        purpose_code=purpose_code,
        purpose_description=purpose_description or desc,
        is_education_loan=str(is_education_loan).lower(),
        status=TransactionStatus.INITIATED,
        beneficiary_id=beneficiary_id,
    )
    db.add(tx)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        )
        return result.scalar_one()

    # Add initial event directly to session (no lazy-load)
    db.add(TransactionEvent(
        transaction_id=tx.id,
        from_status=None,
        to_status=TransactionStatus.INITIATED,
        note="Transaction created",
    ))
    await db.flush()
    return tx


def _transition(
    db: AsyncSession,
    tx: Transaction,
    new_status: TransactionStatus,
    note: str = "",
) -> None:
    allowed = ALLOWED_TRANSITIONS.get(tx.status, set())
    if new_status not in allowed:
        raise InvalidStateMachineTransitionError(
            f"Cannot transition {tx.status} → {new_status}"
        )
    db.add(TransactionEvent(
        transaction_id=tx.id,
        from_status=tx.status,
        to_status=new_status,
        note=note,
    ))
    tx.status = new_status


async def execute_transaction(db: AsyncSession, transaction_id: str) -> Transaction:
    """
    Full lifecycle:
      INITIATED → RATE_LOCKED → COMPLIANCE_CHECK → FUNDS_DEBITED
               → FX_EXECUTED → FUNDS_CREDITED → SETTLED
    """
    tx_uuid = uuid_module.UUID(transaction_id) if isinstance(transaction_id, str) else transaction_id
    result = await db.execute(select(Transaction).where(Transaction.id == tx_uuid))
    tx = result.scalar_one_or_none()
    if tx is None:
        raise ValueError(f"Transaction {transaction_id} not found")

    try:
        # ── 1. Lock rate ──────────────────────────────────────────────────────
        rate, expires_at = await fx_rate_svc.lock_rate(db, str(tx.id))
        amount_usd = (Decimal(str(tx.amount_inr)) / rate).quantize(Decimal("0.0001"))
        tx.exchange_rate = rate
        tx.amount_usd = amount_usd
        tx.rate_lock_expires_at = expires_at
        _transition(db, tx, TransactionStatus.RATE_LOCKED, f"Rate locked at {rate} INR/USD")

        # ── 2. Compliance check ───────────────────────────────────────────────
        _transition(db, tx, TransactionStatus.COMPLIANCE_CHECK, "Running compliance checks")
        await compliance_svc.check_lrs_limit(db, tx.user_id, amount_usd)

        is_edu_loan = tx.is_education_loan == "true"
        tcs_rate, tcs_amount = compliance_svc.calculate_tcs(
            Decimal(str(tx.amount_inr)), tx.purpose_code, is_edu_loan
        )
        tx.tcs_amount = tcs_amount

        if tcs_amount > 0:
            await compliance_svc.record_tcs(
                db,
                str(tx.id),
                tx.user_id,
                tx.purpose_code,
                tcs_rate,
                Decimal(str(tx.amount_inr)),
                tcs_amount,
            )

        # ── 3. Debit INR ──────────────────────────────────────────────────────
        _transition(db, tx, TransactionStatus.FUNDS_DEBITED, "INR debited from customer")
        await ledger_svc.record_inr_debit(db, str(tx.id), Decimal(str(tx.amount_inr)), tcs_amount)

        # ── 4. Execute FX ─────────────────────────────────────────────────────
        _transition(db, tx, TransactionStatus.FX_EXECUTED, f"FX executed: {tx.amount_inr} INR → {amount_usd} USD")
        await ledger_svc.record_fx_conversion(
            db, str(tx.id), Decimal(str(tx.amount_inr)) - tcs_amount, amount_usd
        )
        tx.fx_reference_id = f"WISE-STUB-{str(tx.id)[:8].upper()}"

        # ── 5. Credit USD (internal ledger) ───────────────────────────────────
        _transition(db, tx, TransactionStatus.FUNDS_CREDITED, f"USD {amount_usd} credited to nostro")
        await ledger_svc.record_usd_credit(db, str(tx.id), amount_usd)

        # ── 6. Update LRS ─────────────────────────────────────────────────────
        await compliance_svc.update_lrs_usage(db, tx.user_id, amount_usd)

        # ── 7. Submit LOCAL payment via Airwallex (replaces SWIFT) ───────────
        _transition(db, tx, TransactionStatus.PAYOUT_PENDING, "Payment submitted to Airwallex LOCAL rails")
        payment = await _submit_airwallex_payment(db, tx, amount_usd)
        tx.payout_order_id = payment.payment_id
        await db.flush()
        # Settlement is async — Airwallex calls our webhook when PAID.
        # The Celery task polls as a fallback (see workers/tasks.py).

    except Exception as exc:
        if tx.status not in (TransactionStatus.SETTLED, TransactionStatus.FAILED):
            db.add(TransactionEvent(
                transaction_id=tx.id,
                from_status=tx.status,
                to_status=TransactionStatus.FAILED,
                note=str(exc),
            ))
            tx.status = TransactionStatus.FAILED
            tx.failure_reason = str(exc)
            await db.flush()
        raise

    return tx


async def _submit_airwallex_payment(
    db: AsyncSession,
    tx: Transaction,
    amount_usd: Decimal,
) -> airwallex_svc.AirwallexPaymentResponse:
    """
    Ensure the beneficiary is registered with Airwallex, then submit a LOCAL
    USD payment — bypassing SWIFT entirely.

    Step 1 — Register beneficiary (once, cached): if the Beneficiary doesn't
    have an airwallex_beneficiary_id yet, call Airwallex to register their bank
    account details and cache the returned ID.

    Step 2 — Create payment: submit a LOCAL USD payment from our Airwallex
    wallet. Airwallex routes via domestic ACH/Faster Payments at the destination
    instead of SWIFT, saving fees and delivering same-day or next-day.
    """
    if tx.beneficiary is None:
        raise ValueError(f"Transaction {tx.id} has no beneficiary — cannot route via Airwallex")

    b = tx.beneficiary

    # ── Step 1: register with Airwallex (lazy, cached) ────────────────────────
    if not b.airwallex_beneficiary_id:
        # Use ABA routing for US accounts, SWIFT BIC for international
        is_us = b.country_code == "US"
        ben = await airwallex_svc.create_beneficiary(
            beneficiary_id=str(b.id),
            full_name=b.full_name,
            account_number=b.account_number,
            bank_country_code=b.country_code,
            bank_name=b.bank_name,
            aba=b.routing_number if is_us else None,
            swift_code=b.swift_bic if not is_us else None,
        )
        b.airwallex_beneficiary_id = ben.beneficiary_id
        await db.flush()
        logger.info("Airwallex beneficiary registered for %s: %s", b.id, ben.beneficiary_id)

    # ── Step 2: create LOCAL payment ──────────────────────────────────────────
    return await airwallex_svc.create_payment(
        transaction_id=str(tx.id),
        amount_usd=amount_usd,
        airwallex_beneficiary_id=b.airwallex_beneficiary_id,
        purpose_code=tx.purpose_code,
    )


async def settle_from_airwallex_webhook(
    db: AsyncSession,
    payment_id: str,
    success: bool,
    failure_reason: str | None = None,
) -> Transaction:
    """
    Called by the Airwallex webhook handler.
    Transitions PAYOUT_PENDING → SETTLED or FAILED.
    """
    result = await db.execute(
        select(Transaction).where(Transaction.payout_order_id == payment_id)
    )
    tx = result.scalar_one_or_none()
    if tx is None:
        raise ValueError(f"No transaction found for Airwallex payment_id={payment_id}")

    if success:
        _transition(db, tx, TransactionStatus.SETTLED, f"Airwallex LOCAL payment delivered (payment {payment_id})")
    else:
        db.add(TransactionEvent(
            transaction_id=tx.id,
            from_status=tx.status,
            to_status=TransactionStatus.FAILED,
            note=failure_reason or "Airwallex payment failed",
        ))
        tx.status = TransactionStatus.FAILED
        tx.failure_reason = failure_reason

    await db.flush()
    return tx


async def get_transaction(db: AsyncSession, transaction_id: str) -> Transaction | None:
    tx_uuid = uuid_module.UUID(transaction_id) if isinstance(transaction_id, str) else transaction_id
    result = await db.execute(
        select(Transaction).where(Transaction.id == tx_uuid)
    )
    return result.scalar_one_or_none()


async def list_transactions(
    db: AsyncSession,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Transaction]:
    q = select(Transaction).order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
    if user_id:
        q = q.where(Transaction.user_id == user_id)
    result = await db.execute(q)
    return list(result.scalars().all())
