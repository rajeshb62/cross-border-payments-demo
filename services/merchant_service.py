# DEMO SIMPLIFICATION: Merchant onboarding is instant; no real KYC document flow.
# PRODUCTION TODO: Integrate with a KYC provider (e.g. Onfido, Digio), send verification
#   emails, handle async KYC callbacks, and enforce country-level restrictions.

import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import MerchantNotFoundError
from models.merchant import Merchant, MerchantStatus, VirtualAccount


def _generate_account_number() -> str:
    """Generate a simulated 12-digit Indian virtual account number."""
    return str(random.randint(100_000_000_000, 999_999_999_999))


async def create_merchant(data: dict, db: AsyncSession) -> Merchant:
    """Create a new merchant and auto-provision a virtual account."""
    merchant = Merchant(
        name=data["name"],
        email=data["email"],
        country=data["country"],
        settlement_currency=data["settlement_currency"],
        settlement_account_details=data.get("settlement_account_details", {}),
        status=MerchantStatus.active,  # Demo: skip KYC, activate immediately
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


async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession) -> Merchant:
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise MerchantNotFoundError(f"Merchant {merchant_id} not found")
    return merchant


async def list_merchants(db: AsyncSession) -> list[Merchant]:
    result = await db.execute(select(Merchant))
    return list(result.scalars().all())
