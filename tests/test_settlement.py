"""Tests: settlement amount calculation and reconciliation log creation."""
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from models.merchant import Merchant, VirtualAccount, MerchantStatus, SettlementCurrency, KYBStatus
from models.transaction import TransactionStatus
from models.reconciliation import ReconciliationLog
from services.payment_service import initiate_payment, simulate_inr_collection
from services.settlement_service import process_settlement
from sqlalchemy import select


async def _setup_merchant(db, email, currency=SettlementCurrency.USD):
    import random
    merchant = Merchant(
        name="Settlement Test", email=email, country="US",
        settlement_currency=currency,
        settlement_account_details={"bank_name": "Chase", "account_number": "111", "swift": "CHASUS33"},
        status=MerchantStatus.active,
        kyb_status=KYBStatus.APPROVED,
    )
    db.add(merchant)
    await db.flush()
    va = VirtualAccount(
        merchant_id=merchant.id,
        inr_account_number=str(random.randint(100_000_000_000, 999_999_999_999)),
        ifsc_code="CROSS_BORDER_APP0001", is_active=True,
    )
    db.add(va)
    await db.commit()
    return merchant


async def _mock_get_rate(from_cur, to_cur, db):
    rates = {
        ("INR", "USD"): Decimal("83.5"),
        ("INR", "SGD"): Decimal("62.2"),
        ("INR", "AED"): Decimal("22.7"),
        ("INR", "GBP"): Decimal("105.3"),
        ("INR", "HKD"): Decimal("10.7"),
    }
    return rates.get((from_cur, to_cur), Decimal("83.5"))


@pytest.mark.asyncio
async def test_settlement_computes_correct_amount(db):
    """settlement_amount = (inr_amount - fee_inr) / fx_rate_locked"""
    merchant = await _setup_merchant(db, "settle1@test.io")
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        tx = await initiate_payment(
            merchant_id=merchant.id, inr_amount=Decimal("83500"),
            payment_method="upi", purpose_code="P0802",
            payer_upi_id=None, payer_bank=None, db=db,
        )
    tx = await simulate_inr_collection(tx.id, db)

    # settlement_service uses the locked rate (83.5) — no need to mock convert
    tx = await process_settlement(tx.id, db)

    assert tx.status == TransactionStatus.settled
    assert tx.fx_rate == Decimal("83.5")
    # fee_inr = 83500 * 1.5% = 1252.50; fee_in_settlement = 1252.50 / 83.5 = 15.0000
    # gross = 83500 / 83.5 = 1000.0000; net = 1000 - 15 = 985.0000
    assert tx.settlement_amount == Decimal("985.0000")


@pytest.mark.asyncio
async def test_settlement_creates_reconciliation_log(db):
    merchant = await _setup_merchant(db, "settle2@test.io")
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        tx = await initiate_payment(
            merchant_id=merchant.id, inr_amount=Decimal("50000"),
            payment_method="card", purpose_code="P0802",
            payer_upi_id=None, payer_bank=None, db=db,
        )
    tx = await simulate_inr_collection(tx.id, db)
    tx = await process_settlement(tx.id, db)

    result = await db.execute(
        select(ReconciliationLog).where(ReconciliationLog.transaction_id == tx.id)
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.status.value in ("matched", "mismatch")
