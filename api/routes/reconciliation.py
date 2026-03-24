import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.reconciliation import ReconciliationLog, ReconciliationStatus

router = APIRouter()


class ReconciliationOut(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    expected_settlement_amount: Decimal
    actual_settlement_amount: Decimal
    status: ReconciliationStatus
    checked_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ReconciliationOut])
async def get_reconciliation_logs(db: AsyncSession = Depends(get_db)):
    """Return recent reconciliation log entries (last 100)."""
    result = await db.execute(
        select(ReconciliationLog)
        .order_by(desc(ReconciliationLog.checked_at))
        .limit(100)
    )
    return list(result.scalars().all())
