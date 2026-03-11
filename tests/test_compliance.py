"""Tests for LRS limits and TCS calculations per purpose code."""
import uuid
from decimal import Decimal

import pytest

from core.exceptions import ComplianceError, LRSLimitExceededError
from services.compliance import (
    calculate_tcs,
    check_lrs_limit,
    update_lrs_usage,
    validate_purpose_code,
)


# ── Purpose code validation ───────────────────────────────────────────────────

def test_valid_purpose_code():
    desc = validate_purpose_code("P0001")
    assert "maintenance" in desc.lower()


def test_invalid_purpose_code():
    with pytest.raises(ComplianceError):
        validate_purpose_code("INVALID")


# ── TCS calculation ───────────────────────────────────────────────────────────

def test_tcs_education_via_loan():
    rate, amount = calculate_tcs(Decimal("835000"), "P0002", is_education_loan=True)
    assert rate == Decimal("0.005")
    assert amount == (Decimal("835000") * Decimal("0.005")).quantize(Decimal("0.01"))


def test_tcs_education_self_financed():
    rate, amount = calculate_tcs(Decimal("835000"), "P0002", is_education_loan=False)
    assert rate == Decimal("0.05")
    assert amount == (Decimal("835000") * Decimal("0.05")).quantize(Decimal("0.01"))


def test_tcs_medical():
    rate, amount = calculate_tcs(Decimal("500000"), "P0003")
    assert rate == Decimal("0.05")
    assert amount == (Decimal("500000") * Decimal("0.05")).quantize(Decimal("0.01"))


def test_tcs_general_below_threshold():
    # ₹5L < ₹7L threshold → 0%
    rate, amount = calculate_tcs(Decimal("500000"), "P0001")
    assert rate == Decimal("0")
    assert amount == Decimal("0")


def test_tcs_general_above_threshold():
    # ₹10L > ₹7L → 20% on ₹3L = ₹60,000
    rate, amount = calculate_tcs(Decimal("1000000"), "P0001")
    assert rate == Decimal("0.20")
    assert amount == Decimal("60000.00")


def test_tcs_general_exactly_at_threshold():
    rate, amount = calculate_tcs(Decimal("700000"), "P0001")
    assert rate == Decimal("0")
    assert amount == Decimal("0")


# ── LRS limit ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lrs_check_passes_for_new_user(db):
    record = await check_lrs_limit(db, f"new_user_{uuid.uuid4()}", Decimal("10000"))
    assert record is not None


@pytest.mark.asyncio
async def test_lrs_check_fails_when_exceeded(db):
    user_id = f"heavy_user_{uuid.uuid4()}"
    await update_lrs_usage(db, user_id, Decimal("245000"))
    await db.commit()

    with pytest.raises(LRSLimitExceededError):
        await check_lrs_limit(db, user_id, Decimal("10000"))


@pytest.mark.asyncio
async def test_lrs_usage_accumulates(db):
    user_id = f"accumulate_user_{uuid.uuid4()}"
    await update_lrs_usage(db, user_id, Decimal("10000"))
    await update_lrs_usage(db, user_id, Decimal("5000"))
    await db.commit()

    record = await check_lrs_limit(db, user_id, Decimal("1000"))
    assert Decimal(str(record.utilized_usd)) == Decimal("15000")
