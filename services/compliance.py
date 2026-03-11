"""Compliance service — LRS limit checks, TCS calculation, purpose code validation."""
from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import ComplianceError, LRSLimitExceededError
from models.compliance import LRSRecord, TCSRecord

# FEMA purpose codes (subset relevant for retail remittances)
VALID_PURPOSE_CODES: dict[str, str] = {
    "P0001": "Family maintenance and savings",
    "P0002": "Education (including tuition, living expenses)",
    "P0003": "Medical treatment abroad",
    "P0004": "Travel (business/leisure)",
    "P0005": "Gifts and donations",
    "P0006": "Investment in overseas assets",
    "P0007": "Maintenance of close relatives",
    "P0008": "Emigration",
    "P0009": "Employment abroad",
    "P0010": "Other current account transactions",
}


def _current_financial_year() -> str:
    now = datetime.now(timezone.utc)
    if now.month >= 4:
        return f"{now.year}-{now.year + 1}"
    return f"{now.year - 1}-{now.year}"


def validate_purpose_code(purpose_code: str) -> str:
    """Return description or raise ComplianceError."""
    if purpose_code not in VALID_PURPOSE_CODES:
        raise ComplianceError(
            f"Invalid purpose code '{purpose_code}'. "
            f"Valid codes: {', '.join(VALID_PURPOSE_CODES.keys())}"
        )
    return VALID_PURPOSE_CODES[purpose_code]


async def check_lrs_limit(
    db: AsyncSession,
    user_id: str,
    amount_usd: Decimal,
) -> LRSRecord:
    """Raise LRSLimitExceededError if transaction would breach $250K annual cap."""
    fy = _current_financial_year()
    result = await db.execute(
        select(LRSRecord).where(
            LRSRecord.user_id == user_id,
            LRSRecord.financial_year == fy,
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = LRSRecord(
            user_id=user_id,
            financial_year=fy,
            utilized_usd=Decimal("0"),
            limit_usd=Decimal(str(settings.MAX_LRS_LIMIT_USD)),
        )
        db.add(record)
        await db.flush()

    remaining = Decimal(str(record.limit_usd)) - Decimal(str(record.utilized_usd))
    if amount_usd > remaining:
        raise LRSLimitExceededError(
            f"Transaction of ${amount_usd:.2f} would exceed LRS limit. "
            f"Remaining: ${remaining:.2f} for FY {fy}."
        )
    return record


async def update_lrs_usage(
    db: AsyncSession,
    user_id: str,
    amount_usd: Decimal,
) -> LRSRecord:
    """Increment LRS utilization after successful transaction."""
    fy = _current_financial_year()
    result = await db.execute(
        select(LRSRecord).where(
            LRSRecord.user_id == user_id,
            LRSRecord.financial_year == fy,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        record = LRSRecord(
            user_id=user_id,
            financial_year=fy,
            utilized_usd=amount_usd,
            limit_usd=Decimal(str(settings.MAX_LRS_LIMIT_USD)),
        )
        db.add(record)
    else:
        record.utilized_usd = Decimal(str(record.utilized_usd)) + amount_usd
    await db.flush()
    return record


def calculate_tcs(
    amount_inr: Decimal,
    purpose_code: str,
    is_education_loan: bool = False,
) -> tuple[Decimal, Decimal]:
    """
    Return (tcs_rate, tcs_amount_inr).

    Rules:
    - P0002 + education loan flag → 0.5%
    - P0002 (self-financed) or P0003 (medical) → 5%
    - All others:
        - Below ₹7L threshold → 0%
        - Above ₹7L threshold → 20% on amount above threshold
    """
    threshold = Decimal(str(settings.TCS_THRESHOLD_INR))

    if purpose_code == "P0002" and is_education_loan:
        rate = Decimal("0.005")
        return rate, (amount_inr * rate).quantize(Decimal("0.01"))

    if purpose_code in ("P0002", "P0003"):
        rate = Decimal("0.05")
        return rate, (amount_inr * rate).quantize(Decimal("0.01"))

    # General rule: 20% above ₹7L
    if amount_inr <= threshold:
        return Decimal("0"), Decimal("0")

    taxable = amount_inr - threshold
    rate = Decimal("0.20")
    return rate, (taxable * rate).quantize(Decimal("0.01"))


async def record_tcs(
    db: AsyncSession,
    transaction_id: str,
    user_id: str,
    purpose_code: str,
    tcs_rate: Decimal,
    taxable_amount_inr: Decimal,
    tcs_amount_inr: Decimal,
) -> TCSRecord:
    tx_uuid = uuid_module.UUID(transaction_id) if isinstance(transaction_id, str) else transaction_id
    record = TCSRecord(
        transaction_id=tx_uuid,
        user_id=user_id,
        purpose_code=purpose_code,
        tcs_rate=tcs_rate,
        taxable_amount_inr=taxable_amount_inr,
        tcs_amount_inr=tcs_amount_inr,
        financial_year=_current_financial_year(),
    )
    db.add(record)
    await db.flush()
    return record
