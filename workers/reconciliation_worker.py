"""
Periodic reconciliation task — runs every 60s via Celery beat.
Checks settled transactions from the last 24h and creates/updates ReconciliationLog entries.
"""
import asyncio
from datetime import datetime, timezone, timedelta

from workers.celery_app import celery_app


@celery_app.task(name="workers.reconciliation_worker.reconcile_settlements")
def reconcile_settlements() -> dict:
    """
    Periodic task: find settled transactions from last 24h without a reconciliation log
    and create pending entries for them.
    """
    async def _run():
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from core.config import settings
        from models.transaction import Transaction, TransactionStatus
        from models.reconciliation import ReconciliationLog, ReconciliationStatus

        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        checked = 0

        async with session_factory() as db:
            result = await db.execute(
                select(Transaction)
                .where(Transaction.status == TransactionStatus.settled)
                .where(Transaction.updated_at >= cutoff)
            )
            transactions = result.scalars().all()

            for tx in transactions:
                # Check if already reconciled
                existing = await db.execute(
                    select(ReconciliationLog).where(ReconciliationLog.transaction_id == tx.id)
                )
                if existing.scalar_one_or_none():
                    continue

                # Create pending entry (settlement_service already creates one normally;
                # this catches any that slipped through)
                recon = ReconciliationLog(
                    transaction_id=tx.id,
                    expected_settlement_amount=tx.settlement_amount,
                    actual_settlement_amount=tx.settlement_amount,
                    status=ReconciliationStatus.pending,
                )
                db.add(recon)
                checked += 1

            await db.commit()
        return {"checked": checked}

    return asyncio.run(_run())
