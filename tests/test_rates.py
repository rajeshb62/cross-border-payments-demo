"""Tests for rate locking, Redis TTL expiry, and rate history."""
import json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio

from core.exceptions import RateLockExpiredError
from services.fx_rate import get_live_rate, get_locked_rate, lock_rate


@pytest.mark.asyncio
async def test_get_live_rate_returns_stub(db):
    rate = await get_live_rate("INR", "USD")
    assert rate == Decimal("83.5")


@pytest.mark.asyncio
async def test_get_live_rate_unsupported_pair(db):
    from core.exceptions import FXError
    with pytest.raises(FXError):
        await get_live_rate("EUR", "JPY")


@pytest.mark.asyncio
async def test_lock_rate_stores_in_redis(db, fake_redis):
    tx_id = str(uuid.uuid4())
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        rate, expires_at = await lock_rate(db, tx_id)
        await db.commit()

    assert rate == Decimal("83.5")
    assert expires_at is not None

    # Verify it's in fake Redis
    key = f"rate_lock:{tx_id}"
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        data = await fake_redis.get(key)
    assert data is not None
    payload = json.loads(data)
    assert Decimal(payload["rate"]) == Decimal("83.5")


@pytest.mark.asyncio
async def test_get_locked_rate_from_redis(db, fake_redis):
    tx_id = str(uuid.uuid4())
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        await lock_rate(db, tx_id)
        await db.commit()
        rate = await get_locked_rate(tx_id, db)

    assert rate == Decimal("83.5")


@pytest.mark.asyncio
async def test_get_locked_rate_raises_when_missing(db, fake_redis):
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        with pytest.raises(RateLockExpiredError):
            await get_locked_rate("nonexistent-tx-id", db)


@pytest.mark.asyncio
async def test_rate_lock_ttl_expiry(db, fake_redis):
    """Simulates TTL expiry by deleting key and checking DB fallback."""
    tx_id = str(uuid.uuid4())
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        await lock_rate(db, tx_id)
        await db.commit()

        # Simulate Redis key expiration
        await fake_redis.delete(f"rate_lock:{tx_id}")

        # Should fall back to DB record (which is not expired yet)
        rate = await get_locked_rate(tx_id, db)
    assert rate == Decimal("83.5")
