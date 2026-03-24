"""Tests: merchant creation auto-creates virtual account."""
import pytest
from sqlalchemy import select

from models.merchant import Merchant, VirtualAccount, SettlementCurrency
from services.merchant_service import create_merchant, get_merchant


@pytest.mark.asyncio
async def test_create_merchant_creates_virtual_account(db):
    data = {
        "name": "Test Corp",
        "email": "test@testcorp.io",
        "country": "US",
        "settlement_currency": SettlementCurrency.USD,
        "settlement_account_details": {"bank_name": "Chase", "account_number": "123", "swift": "CHASUS33"},
    }
    merchant = await create_merchant(data, db)
    assert merchant.id is not None
    assert len(merchant.virtual_accounts) == 1
    va = merchant.virtual_accounts[0]
    assert len(va.inr_account_number) == 12
    assert va.ifsc_code == "EXIMPE0001"
    assert va.is_active is True


@pytest.mark.asyncio
async def test_get_merchant_not_found(db):
    import uuid
    from core.exceptions import MerchantNotFoundError
    with pytest.raises(MerchantNotFoundError):
        await get_merchant(uuid.uuid4(), db)


@pytest.mark.asyncio
async def test_create_merchant_status_active(db):
    data = {
        "name": "Active Co",
        "email": "active@co.io",
        "country": "DE",
        "settlement_currency": SettlementCurrency.EUR,
        "settlement_account_details": {"bank_name": "DB", "account_number": "456", "swift": "DEUTDEDB"},
    }
    merchant = await create_merchant(data, db)
    assert merchant.status.value == "active"
