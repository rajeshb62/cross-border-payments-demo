import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.merchant import SettlementCurrency
from services import merchant_service

router = APIRouter()


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
    virtual_accounts: list[VirtualAccountOut] = []

    model_config = {"from_attributes": True}


@router.post("", response_model=MerchantOut, status_code=201)
async def create_merchant(body: MerchantCreate, db: AsyncSession = Depends(get_db)):
    return await merchant_service.create_merchant(body.model_dump(), db)


@router.get("/{merchant_id}", response_model=MerchantOut)
async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await merchant_service.get_merchant(merchant_id, db)


@router.get("", response_model=list[MerchantOut])
async def list_merchants(db: AsyncSession = Depends(get_db)):
    return await merchant_service.list_merchants(db)
