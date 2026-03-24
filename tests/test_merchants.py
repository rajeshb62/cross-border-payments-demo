"""Tests: merchant creation, onboarding, and virtual account provisioning."""
import pytest
from sqlalchemy import select

from models.merchant import Merchant, VirtualAccount, SettlementCurrency, KYBStatus
from services.merchant_service import create_merchant, get_merchant, onboard_merchant


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
        "settlement_currency": SettlementCurrency.USD,
        "settlement_account_details": {"bank_name": "DB", "account_number": "456", "swift": "DEUTDEDB"},
    }
    merchant = await create_merchant(data, db)
    assert merchant.status.value == "active"
    # Direct create_merchant sets kyb_status to APPROVED for backward compat
    assert merchant.kyb_status == KYBStatus.APPROVED


@pytest.mark.asyncio
async def test_onboard_merchant_creates_pending_kyb(db):
    """Onboarded merchants start with PENDING kyb_status."""
    data = {
        "business_name": "Acme SaaS Ltd",
        "contact_email": "acme@saas.io",
        "country": "SG",
        "business_type": "SAAS",
        "website_url": "https://acme.io",
        "settlement_currency": SettlementCurrency.SGD,
        "incorporation_number": "SG2024001",
    }
    merchant = await onboard_merchant(data, db)
    assert merchant.id is not None
    assert merchant.kyb_status == KYBStatus.PENDING
    assert merchant.name == "Acme SaaS Ltd"
    assert merchant.country == "SG"
    assert len(merchant.virtual_accounts) == 1


@pytest.mark.asyncio
async def test_onboard_merchant_rejects_indian_merchants(db):
    """Indian merchants cannot be onboarded via OPGSP flow."""
    data = {
        "business_name": "India Co",
        "contact_email": "india@co.in",
        "country": "IN",
        "business_type": "ECOMMERCE",
        "settlement_currency": SettlementCurrency.USD,
        "incorporation_number": "IN2024001",
    }
    with pytest.raises(ValueError, match="Indian merchants cannot be onboarded"):
        await onboard_merchant(data, db)
