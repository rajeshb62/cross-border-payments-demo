"""
KYB auto-approval worker — simulates 48-hour review.
In dev/test, approves after 10 seconds.
"""
import asyncio
import uuid
from workers.celery_app import celery_app


@celery_app.task(name="workers.kyb_worker.auto_approve_kyb")
def auto_approve_kyb(merchant_id: str) -> dict:
    import time
    time.sleep(10)  # Simulate 48h review; 10s in demo

    async def _run():
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from core.config import settings
        from models.merchant import Merchant, KYBStatus

        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with session_factory() as db:
            result = await db.execute(select(Merchant).where(Merchant.id == uuid.UUID(merchant_id)))
            merchant = result.scalar_one_or_none()
            if merchant and merchant.kyb_status == KYBStatus.PENDING:
                merchant.kyb_status = KYBStatus.UNDER_REVIEW
                await db.commit()
                await asyncio.sleep(2)
                merchant.kyb_status = KYBStatus.APPROVED
                await db.commit()
        return {"merchant_id": merchant_id, "kyb_status": "APPROVED"}

    return asyncio.run(_run())
