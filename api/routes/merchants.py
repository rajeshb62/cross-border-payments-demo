import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.merchant import SettlementCurrency, BusinessType, KYBStatus
from services import merchant_service

router = APIRouter()

# Active OPGSP settlement currencies (restricted at API layer)
OPGSPCurrency = Literal["USD", "SGD", "AED", "GBP", "HKD"]


class SettlementAccountDetails(BaseModel):
    bank_name: str
    account_number: str
    swift: str


class MerchantCreate(BaseModel):
    name: str
    email: str
    country: str
    settlement_currency: SettlementCurrency
    settlement_account_details: SettlementAccountDetails


class MerchantOnboard(BaseModel):
    business_name: str
    country: str
    business_type: BusinessType
    website_url: Optional[str] = None
    settlement_currency: SettlementCurrency
    contact_email: str
    incorporation_number: Optional[str] = None


class VirtualAccountOut(BaseModel):
    id: uuid.UUID
    inr_account_number: str
    ifsc_code: str
    is_active: bool

    model_config = {"from_attributes": True}


class MerchantOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    country: str
    settlement_currency: SettlementCurrency
    settlement_account_details: dict
    status: str
    kyb_status: str
    virtual_accounts: list[VirtualAccountOut] = []

    model_config = {"from_attributes": True}


@router.post("", response_model=MerchantOut, status_code=201)
async def create_merchant(body: MerchantCreate, db: AsyncSession = Depends(get_db)):
    return await merchant_service.create_merchant(body.model_dump(), db)


@router.post("/onboard", response_model=MerchantOut, status_code=201)
async def onboard_merchant(body: MerchantOnboard, db: AsyncSession = Depends(get_db)):
    """
    Onboard a new foreign merchant via OPGSP KYB flow.
    Merchant starts with PENDING kyb_status; a background task moves to APPROVED after review.
    """
    try:
        return await merchant_service.onboard_merchant(body.model_dump(), db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{merchant_id}", response_model=MerchantOut)
async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await merchant_service.get_merchant(merchant_id, db)


@router.get("", response_model=list[MerchantOut])
async def list_merchants(db: AsyncSession = Depends(get_db)):
    return await merchant_service.list_merchants(db)
