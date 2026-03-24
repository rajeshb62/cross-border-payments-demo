"""
Periodic FX rate refresh task — runs every 60s via Celery beat.
Fetches latest rates for all 7 settlement currencies from frankfurter.app.
"""
import asyncio

from workers.celery_app import celery_app


@celery_app.task(name="workers.fx_worker.refresh_fx_rates")
def refresh_fx_rates() -> dict:
    """Fetch and cache INR→{currency} rates for all settlement currencies."""
    async def _run():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from core.config import settings
        from services.fx_service import refresh_all_rates

        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with session_factory() as db:
            await refresh_all_rates(db)
        return {"status": "refreshed"}

    return asyncio.run(_run())
