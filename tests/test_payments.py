"""Tests: payment initiation, OPGSP cap, UPI intent generation, state transitions."""
import pytest
import uuid
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from models.merchant import Merchant, VirtualAccount, MerchantStatus, SettlementCurrency, KYBStatus
from models.transaction import TransactionStatus
from services.payment_service import initiate_payment, simulate_inr_collection
from core.exceptions import InvalidTransactionStateError, OGPSPLimitExceededError, MerchantNotApprovedError


async def _create_merchant_with_va(db, email="pay@test.io", currency=SettlementCurrency.USD):
    """Helper to create a KYB-approved merchant + VA for payment tests."""
    import random
    merchant = Merchant(
        name="Pay Test",
        email=email,
        country="US",
        settlement_currency=currency,
        settlement_account_details={"bank_name": "Chase", "account_number": "000", "swift": "CHASUS33"},
        status=MerchantStatus.active,
        kyb_status=KYBStatus.APPROVED,
    )
    db.add(merchant)
    await db.flush()
    va = VirtualAccount(
        merchant_id=merchant.id,
        inr_account_number=str(random.randint(100_000_000_000, 999_999_999_999)),
        ifsc_code="EXIMPE0001",
        is_active=True,
    )
    db.add(va)
    await db.commit()
    return merchant


# Fixed mock rate: 1 USD = 83.5 INR  →  rate returned = 83.5
MOCK_RATE_USD = Decimal("83.5")

async def _mock_get_rate(from_cur, to_cur, db):
    """Return a fixed rate for any currency pair."""
    rates = {
        ("INR", "USD"): Decimal("83.5"),
        ("INR", "SGD"): Decimal("62.2"),
        ("INR", "AED"): Decimal("22.7"),
        ("INR", "GBP"): Decimal("105.3"),
        ("INR", "HKD"): Decimal("10.7"),
    }
    return rates.get((from_cur, to_cur), Decimal("83.5"))


@pytest.mark.asyncio
async def test_initiate_payment_creates_transaction(db):
    merchant = await _create_merchant_with_va(db, email="initpay@test.io")
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        tx = await initiate_payment(
            merchant_id=merchant.id,
            inr_amount=Decimal("50000"),
            payment_method="upi",
            purpose_code="P0802",
            payer_upi_id="payer@upi",
            payer_bank=None,
            db=db,
        )
    assert tx.status == TransactionStatus.initiated
    assert tx.fee_inr == Decimal("750.00")  # 1.5% of 50000
    # UPI intent fields should be populated
    assert tx.vpa is not None
    assert tx.upi_deep_link is not None
    assert "upi://pay" in tx.upi_deep_link
    assert tx.opgsp_ref is not None
    assert tx.fx_rate_locked == MOCK_RATE_USD
    assert tx.usd_equivalent is not None


@pytest.mark.asyncio
async def test_simulate_inr_collection_transitions_status(db):
    merchant = await _create_merchant_with_va(db, email="collect@test.io")
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        tx = await initiate_payment(
            merchant_id=merchant.id,
            inr_amount=Decimal("10000"),
            payment_method="netbanking",
            purpose_code="P0802",
            payer_upi_id=None,
            payer_bank=None,
            db=db,
        )
    tx = await simulate_inr_collection(tx.id, db)
    assert tx.status == TransactionStatus.inr_collected


@pytest.mark.asyncio
async def test_simulate_inr_collection_wrong_state_raises(db):
    merchant = await _create_merchant_with_va(db, email="wrongstate@test.io")
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        tx = await initiate_payment(
            merchant_id=merchant.id,
            inr_amount=Decimal("10000"),
            payment_method="card",
            purpose_code="P0802",
            payer_upi_id=None,
            payer_bank=None,
            db=db,
        )
    # First collection is fine
    await simulate_inr_collection(tx.id, db)
    # Second should fail
    with pytest.raises(InvalidTransactionStateError):
        await simulate_inr_collection(tx.id, db)


@pytest.mark.asyncio
async def test_opgsp_cap_exceeded_raises(db):
    """Amount > $10,000 USD should raise OGPSPLimitExceededError."""
    merchant = await _create_merchant_with_va(db, email="captest@test.io")
    # 1,000,000 INR / 83.5 = ~11,976 USD > 10,000 cap
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        with pytest.raises(OGPSPLimitExceededError):
            await initiate_payment(
                merchant_id=merchant.id,
                inr_amount=Decimal("1000000"),
                payment_method="upi",
                purpose_code="P0802",
                payer_upi_id=None,
                payer_bank=None,
                db=db,
            )


@pytest.mark.asyncio
async def test_opgsp_cap_at_boundary_passes(db):
    """Amount just under $10,000 USD should succeed."""
    merchant = await _create_merchant_with_va(db, email="capboundary@test.io")
    # 835,000 INR / 83.5 = 10,000 USD exactly — should be rejected (> not >=)
    # Use 834,900 INR / 83.5 = 9,998.8 USD — should pass
    with patch("services.payment_service.fx_service.get_rate", side_effect=_mock_get_rate):
        tx = await initiate_payment(
            merchant_id=merchant.id,
            inr_amount=Decimal("834900"),
            payment_method="upi",
            purpose_code="P0802",
            payer_upi_id=None,
            payer_bank=None,
            db=db,
        )
    assert tx.status == TransactionStatus.initiated
    assert tx.usd_equivalent < Decimal("10000")


@pytest.mark.asyncio
async def test_merchant_not_approved_raises(db):
    """Payment should be rejected if merchant KYB is not APPROVED."""
    import random
    pending_merchant = Merchant(
        name="Pending Merchant",
        email="pending@test.io",
        country="UK",
        settlement_currency=SettlementCurrency.GBP,
        settlement_account_details={},
        status=MerchantStatus.pending_kyc,
        kyb_status=KYBStatus.PENDING,
    )
    db.add(pending_merchant)
    await db.flush()
    va = VirtualAccount(
        merchant_id=pending_merchant.id,
        inr_account_number=str(random.randint(100_000_000_000, 999_999_999_999)),
        ifsc_code="EXIMPE0001",
        is_active=True,
    )
    db.add(va)
    await db.commit()

    with pytest.raises(MerchantNotApprovedError):
        await initiate_payment(
            merchant_id=pending_merchant.id,
            inr_amount=Decimal("10000"),
            payment_method="upi",
            purpose_code="P0802",
            payer_upi_id=None,
            payer_bank=None,
            db=db,
        )
