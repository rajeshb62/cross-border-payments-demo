"""
Payment pipeline Celery task.
Chains: simulate_inr_collection → process_settlement with 2s delay between steps.
Supports both direct simulation flow and webhook-triggered (upi_confirmed) flow.
"""
import asyncio
import uuid

from workers.celery_app import celery_app


@celery_app.task(name="workers.payment_worker.process_payment_pipeline", bind=True, max_retries=3)
def process_payment_pipeline(self, transaction_id: str) -> dict:
    """
    Runs the full payment pipeline for a transaction:
    - If status is 'initiated': simulate INR collection first, then settle
    - If status is 'upi_confirmed' or 'inr_collected': go straight to settlement
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from core.config import settings

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with session_factory() as db:
            from sqlalchemy import select
            from models.transaction import Transaction, TransactionStatus
            from services.payment_service import simulate_inr_collection
            from services.settlement_service import process_settlement

            tx_uuid = uuid.UUID(transaction_id)

            # Fetch current status
            result = await db.execute(select(Transaction).where(Transaction.id == tx_uuid))
            tx = result.scalar_one_or_none()
            if not tx:
                return {"transaction_id": transaction_id, "status": "not_found"}

            # Step 1: If still initiated, simulate INR collection
            if tx.status == TransactionStatus.initiated:
                tx = await simulate_inr_collection(tx_uuid, db)
                await asyncio.sleep(2)  # Simulate processing delay

            # Step 2: If inr_collected or upi_confirmed, proceed to settlement
            if tx.status in (TransactionStatus.inr_collected, TransactionStatus.upi_confirmed):
                tx = await process_settlement(tx_uuid, db)

            return {"transaction_id": transaction_id, "status": tx.status.value}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
