# DEMO SIMPLIFICATION: Merchant onboarding is instant; no real KYC document flow.
# PRODUCTION TODO: Integrate with a KYC provider (e.g. Onfido, Digio), send verification
#   emails, handle async KYC callbacks, and enforce country-level restrictions.

import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import MerchantNotFoundError, MerchantNotApprovedError
from models.merchant import Merchant, MerchantStatus, KYBStatus, BusinessType, VirtualAccount


def _generate_account_number() -> str:
    """Generate a simulated 12-digit Indian virtual account number."""
    return str(random.randint(100_000_000_000, 999_999_999_999))


async def create_merchant(data: dict, db: AsyncSession) -> Merchant:
    """Create a new merchant and auto-provision a virtual account. Sets KYB to APPROVED for seeding."""
    merchant = Merchant(
        name=data["name"],
        email=data["email"],
        country=data["country"],
        settlement_currency=data["settlement_currency"],
        settlement_account_details=data.get("settlement_account_details", {}),
        status=MerchantStatus.active,  # Demo: skip KYC, activate immediately
        kyb_status=KYBStatus.APPROVED,  # Backward compat: direct creates are auto-approved
    )
    db.add(merchant)
    await db.flush()  # get merchant.id before creating VA

    virtual_account = VirtualAccount(
        merchant_id=merchant.id,
        inr_account_number=_generate_account_number(),
        ifsc_code="EXIMPE0001",
        is_active=True,
    )
    db.add(virtual_account)
    await db.commit()
    await db.refresh(merchant)
    return merchant


async def onboard_merchant(data: dict, db: AsyncSession) -> Merchant:
    """
    Onboard a new foreign merchant through the OPGSP KYB flow.
    Creates merchant with PENDING kyb_status and triggers async KYB review.
    """
    country = data.get("country", "")
    if country.upper() == "IN":
        raise ValueError("Indian merchants cannot be onboarded via OPGSP flow. Country must be non-IN.")

    merchant = Merchant(
        name=data["business_name"],
        email=data["contact_email"],
        country=country,
        settlement_currency=data["settlement_currency"],
        settlement_account_details={},
        status=MerchantStatus.pending_kyc,
        kyb_status=KYBStatus.PENDING,
        business_type=BusinessType(data["business_type"]) if data.get("business_type") else None,
        website_url=data.get("website_url"),
        incorporation_number=data.get("incorporation_number"),
    )
    db.add(merchant)
    await db.flush()

    virtual_account = VirtualAccount(
        merchant_id=merchant.id,
        inr_account_number=_generate_account_number(),
        ifsc_code="EXIMPE0001",
        is_active=True,
    )
    db.add(virtual_account)
    await db.commit()
    await db.refresh(merchant)

    # Trigger async KYB review (non-blocking)
    try:
        from workers.kyb_worker import auto_approve_kyb
        auto_approve_kyb.delay(str(merchant.id))
    except Exception:
        pass  # Don't fail onboarding if Celery is unavailable (e.g. in tests)

    return merchant


async def check_merchant_approved(merchant_id: uuid.UUID, db: AsyncSession) -> Merchant:
    """Fetch merchant and raise MerchantNotApprovedError if KYB is not APPROVED."""
    merchant = await get_merchant(merchant_id, db)
    if merchant.kyb_status != KYBStatus.APPROVED:
        raise MerchantNotApprovedError(
            f"Merchant {merchant_id} is not approved for payments (kyb_status={merchant.kyb_status.value})"
        )
    return merchant


async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession) -> Merchant:
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise MerchantNotFoundError(f"Merchant {merchant_id} not found")
    return merchant


async def list_merchants(db: AsyncSession) -> list[Merchant]:
    result = await db.execute(select(Merchant))
    return list(result.scalars().all())
