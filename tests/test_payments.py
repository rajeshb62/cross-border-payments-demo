"""Tests: TCS computation, payment initiation, state transitions."""
import pytest
import uuid
from decimal import Decimal

from models.merchant import Merchant, VirtualAccount, MerchantStatus, SettlementCurrency
from models.transaction import TransactionStatus
from services.payment_service import compute_tcs, initiate_payment, simulate_inr_collection
from core.exceptions import InvalidTransactionStateError


async def _create_merchant_with_va(db, email="pay@test.io", currency=SettlementCurrency.USD):
    """Helper to create a merchant + VA for payment tests."""
    import random
    merchant = Merchant(
        name="Pay Test",
        email=email,
        country="US",
        settlement_currency=currency,
        settlement_account_details={"bank_name": "Chase", "account_number": "000", "swift": "CHASUS33"},
        status=MerchantStatus.active,
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


@pytest.mark.asyncio
async def test_tcs_p0802_zero_rate():
    applicable, rate, amount = compute_tcs("P0802", Decimal("500000"))
    assert applicable is False
    assert rate == Decimal("0")
    assert amount == Decimal("0")


@pytest.mark.asyncio
async def test_tcs_p1007_half_percent():
    applicable, rate, amount = compute_tcs("P1007", Decimal("100000"))
    assert applicable is True
    assert rate == Decimal("0.005")
    assert amount == Decimal("500.00")


@pytest.mark.asyncio
async def test_tcs_default_below_threshold():
    applicable, rate, amount = compute_tcs("P0999", Decimal("600000"))
    assert applicable is False
    assert rate == Decimal("0")


@pytest.mark.asyncio
async def test_tcs_default_above_threshold():
    applicable, rate, amount = compute_tcs("P0999", Decimal("900000"))
    assert applicable is True
    assert rate == Decimal("0.20")
    # TCS on amount above 7L threshold: (900000 - 700000) * 0.20 = 40000
    assert amount == Decimal("40000.00")


@pytest.mark.asyncio
async def test_initiate_payment_creates_transaction(db):
    merchant = await _create_merchant_with_va(db, email="initpay@test.io")
    tx = await initiate_payment(
        merchant_id=merchant.id,
        inr_amount=Decimal("50000"),
        payment_method="upi",
        purpose_code="P0802",
        payer_info={"upi_id": "payer@upi"},
        db=db,
    )
    assert tx.status == TransactionStatus.initiated
    assert tx.fee_inr == Decimal("750.00")  # 1.5% of 50000
    assert tx.tcs_applicable is False


@pytest.mark.asyncio
async def test_simulate_inr_collection_transitions_status(db):
    merchant = await _create_merchant_with_va(db, email="collect@test.io")
    tx = await initiate_payment(
        merchant_id=merchant.id,
        inr_amount=Decimal("10000"),
        payment_method="netbanking",
        purpose_code="P0802",
        payer_info={},
        db=db,
    )
    tx = await simulate_inr_collection(tx.id, db)
    assert tx.status == TransactionStatus.inr_collected


@pytest.mark.asyncio
async def test_simulate_inr_collection_wrong_state_raises(db):
    merchant = await _create_merchant_with_va(db, email="wrongstate@test.io")
    tx = await initiate_payment(
        merchant_id=merchant.id,
        inr_amount=Decimal("10000"),
        payment_method="card",
        purpose_code="P0802",
        payer_info={},
        db=db,
    )
    # First collection is fine
    await simulate_inr_collection(tx.id, db)
    # Second should fail
    with pytest.raises(InvalidTransactionStateError):
        await simulate_inr_collection(tx.id, db)
