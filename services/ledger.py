"""Double-entry ledger service."""
from __future__ import annotations

import uuid as uuid_module
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ledger import AccountType, EntryType, LedgerEntry


def _entry(
    transaction_id: str,
    account_type: AccountType,
    entry_type: EntryType,
    currency: str,
    amount: Decimal,
    description: str,
) -> LedgerEntry:
    tx_uuid = uuid_module.UUID(transaction_id) if isinstance(transaction_id, str) else transaction_id
    return LedgerEntry(
        transaction_id=tx_uuid,
        account_type=account_type,
        entry_type=entry_type,
        currency=currency,
        amount=amount,
        description=description,
    )


async def record_inr_debit(
    db: AsyncSession,
    transaction_id: str,
    amount_inr: Decimal,
    tcs_amount: Decimal,
) -> list[LedgerEntry]:
    """
    Customer INR account is debited; FX account is credited.
    TCS portion is split out separately.
    """
    entries = [
        _entry(transaction_id, AccountType.CUSTOMER_INR, EntryType.DEBIT,  "INR", amount_inr,  "Customer INR debit"),
        _entry(transaction_id, AccountType.FX_ACCOUNT,   EntryType.CREDIT, "INR", amount_inr - tcs_amount, "INR received for FX"),
        _entry(transaction_id, AccountType.TCS,          EntryType.CREDIT, "INR", tcs_amount,  "TCS collected"),
    ] if tcs_amount > 0 else [
        _entry(transaction_id, AccountType.CUSTOMER_INR, EntryType.DEBIT,  "INR", amount_inr, "Customer INR debit"),
        _entry(transaction_id, AccountType.FX_ACCOUNT,   EntryType.CREDIT, "INR", amount_inr, "INR received for FX"),
    ]
    for e in entries:
        db.add(e)
    await db.flush()
    return entries


async def record_fx_conversion(
    db: AsyncSession,
    transaction_id: str,
    amount_inr: Decimal,
    amount_usd: Decimal,
) -> list[LedgerEntry]:
    """FX account INR side debited; FX account USD side credited."""
    entries = [
        _entry(transaction_id, AccountType.FX_ACCOUNT, EntryType.DEBIT,  "INR", amount_inr, "INR sold for FX"),
        _entry(transaction_id, AccountType.FX_ACCOUNT, EntryType.CREDIT, "USD", amount_usd, "USD purchased"),
    ]
    for e in entries:
        db.add(e)
    await db.flush()
    return entries


async def record_usd_credit(
    db: AsyncSession,
    transaction_id: str,
    amount_usd: Decimal,
) -> list[LedgerEntry]:
    """FX USD account debited; customer USD account credited."""
    entries = [
        _entry(transaction_id, AccountType.FX_ACCOUNT,   EntryType.DEBIT,  "USD", amount_usd, "USD sent to customer"),
        _entry(transaction_id, AccountType.CUSTOMER_USD, EntryType.CREDIT, "USD", amount_usd, "Customer USD credit"),
    ]
    for e in entries:
        db.add(e)
    await db.flush()
    return entries


async def record_tcs_entry(
    db: AsyncSession,
    transaction_id: str,
    tcs_amount_inr: Decimal,
) -> LedgerEntry:
    entry = _entry(
        transaction_id, AccountType.TCS, EntryType.DEBIT, "INR", tcs_amount_inr, "TCS remitted to government",
    )
    db.add(entry)
    await db.flush()
    return entry


async def daily_reconciliation(db: AsyncSession, for_date: date | None = None) -> dict:
    """
    Sum DEBIT vs CREDIT per currency across all ledger entries.
    Returns mismatch dict (empty = balanced).
    """
    result = await db.execute(
        select(
            LedgerEntry.currency,
            LedgerEntry.entry_type,
            func.sum(LedgerEntry.amount).label("total"),
        ).group_by(LedgerEntry.currency, LedgerEntry.entry_type)
    )
    rows = result.all()

    totals: dict[str, dict[str, Decimal]] = {}
    for currency, entry_type, total in rows:
        totals.setdefault(currency, {"debit": Decimal("0"), "credit": Decimal("0")})
        totals[currency][entry_type] = Decimal(str(total))

    mismatches = {}
    for currency, sums in totals.items():
        diff = sums.get("debit", Decimal("0")) - sums.get("credit", Decimal("0"))
        if abs(diff) > Decimal("0.01"):
            mismatches[currency] = str(diff)

    return {"balanced": len(mismatches) == 0, "mismatches": mismatches, "totals": {k: {ek: str(ev) for ek, ev in v.items()} for k, v in totals.items()}}
