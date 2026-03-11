"""FX rate service — fetches live rate (stubbed via Wise), manages Redis rate locks."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import FXError, RateLockExpiredError
from models.rate import FXRate, RateLock

_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def _rate_lock_key(transaction_id: str) -> str:
    return f"rate_lock:{transaction_id}"


async def get_live_rate(from_currency: str = "INR", to_currency: str = "USD") -> Decimal:
    """Return live mid-market rate. Stubbed to return ~83.5 INR/USD with minor jitter."""
    if from_currency == "INR" and to_currency == "USD":
        # In production: call Wise /v1/rates endpoint
        return Decimal(str(settings.STUB_FX_RATE))
    raise FXError(f"Unsupported currency pair: {from_currency}/{to_currency}")


async def save_rate_history(
    db: AsyncSession,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
    source: str = "wise_stub",
) -> FXRate:
    fx_rate = FXRate(
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate,
        source=source,
    )
    db.add(fx_rate)
    await db.flush()
    return fx_rate


async def lock_rate(
    db: AsyncSession,
    transaction_id: str,
    from_currency: str = "INR",
    to_currency: str = "USD",
) -> tuple[Decimal, datetime]:
    """Fetch live rate, persist to Redis (TTL) + DB, return (rate, expires_at)."""
    rate = await get_live_rate(from_currency, to_currency)
    ttl = settings.RATE_LOCK_TTL_SECONDS
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    # Store in Redis
    redis = _get_redis()
    payload = json.dumps({"rate": str(rate), "expires_at": expires_at.isoformat()})
    await redis.setex(_rate_lock_key(transaction_id), ttl, payload)

    # Persist in DB (upsert-like: delete old if exists)
    existing = await db.execute(
        select(RateLock).where(RateLock.transaction_id == transaction_id)
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row:
        existing_row.locked_rate = rate
        existing_row.expires_at = expires_at
    else:
        db.add(RateLock(
            transaction_id=transaction_id,
            from_currency=from_currency,
            to_currency=to_currency,
            locked_rate=rate,
            expires_at=expires_at,
        ))
    await db.flush()

    # Also save to rate history
    await save_rate_history(db, from_currency, to_currency, rate)

    return rate, expires_at


async def get_locked_rate(transaction_id: str, db: AsyncSession) -> Decimal:
    """Return locked rate for transaction. Raises RateLockExpiredError if gone."""
    redis = _get_redis()
    data = await redis.get(_rate_lock_key(transaction_id))
    if data:
        payload = json.loads(data)
        return Decimal(payload["rate"])

    # Fall back to DB
    result = await db.execute(
        select(RateLock).where(RateLock.transaction_id == transaction_id)
    )
    lock = result.scalar_one_or_none()
    if lock is None:
        raise RateLockExpiredError(f"No rate lock found for transaction {transaction_id}")

    if lock.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise RateLockExpiredError(f"Rate lock expired for transaction {transaction_id}")

    return Decimal(str(lock.locked_rate))
