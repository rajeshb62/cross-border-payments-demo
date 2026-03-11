"""Celery tasks for async transaction processing and scheduled jobs."""
from __future__ import annotations

import asyncio
import logging

from celery.utils.log import get_task_logger

import models.beneficiary  # noqa: F401 — registers Beneficiary with SQLAlchemy mapper
from workers.celery_app import celery_app

logger = get_task_logger(__name__)


def _run_async(coro):
    """Create a fresh event loop per task (required in Celery forked workers)."""
    asyncio.set_event_loop(None)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(None)


def _make_session():
    """Create a fresh async engine + session (avoids reusing forked pool connections)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from core.config import settings
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="workers.tasks.process_transaction",
)
def process_transaction(self, transaction_id: str) -> dict:
    from services.transaction import execute_transaction

    async def _execute():
        SessionLocal = _make_session()
        async with SessionLocal() as db:
            try:
                tx = await execute_transaction(db, transaction_id)
                await db.commit()
                return {"status": tx.status.value, "transaction_id": transaction_id}
            except Exception as exc:
                await db.rollback()
                raise

    try:
        result = _run_async(_execute())
        logger.info("Transaction %s completed: %s", transaction_id, result["status"])
        return result
    except Exception as exc:
        logger.error("Transaction %s failed: %s", transaction_id, str(exc))
        alert_failed_transaction.delay(transaction_id, str(exc))
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for transaction %s", transaction_id)
            return {"status": "failed", "transaction_id": transaction_id, "error": str(exc)}


@celery_app.task(name="workers.tasks.daily_reconciliation_job")
def daily_reconciliation_job() -> dict:
    from services.ledger import daily_reconciliation

    async def _reconcile():
        SessionLocal = _make_session()
        async with SessionLocal() as db:
            result = await daily_reconciliation(db)
            await db.commit()
            return result

    result = _run_async(_reconcile())
    if not result["balanced"]:
        logger.error("RECONCILIATION MISMATCH: %s", result["mismatches"])
    else:
        logger.info("Daily reconciliation passed. Totals: %s", result["totals"])
    return result


@celery_app.task(name="workers.tasks.alert_failed_transaction")
def alert_failed_transaction(transaction_id: str, reason: str) -> None:
    logger.error(
        "ALERT: Transaction %s failed permanently. Reason: %s",
        transaction_id,
        reason,
    )
