"""Tests: FX rate fetch and caching logic."""
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from models.fx_rate import FxRate
from services.fx_service import get_rate, get_all_cached_rates


@pytest.mark.asyncio
async def test_get_rate_cache_miss_fetches_and_caches(db):
    mock_rate = Decimal("83.500000")
    with patch("services.fx_service._fetch_from_frankfurter", new=AsyncMock(return_value=mock_rate)):
        rate = await get_rate("INR", "USD", db)
    assert rate == mock_rate


@pytest.mark.asyncio
async def test_get_rate_uses_cache_when_fresh(db):
    # Insert a fresh rate
    fx = FxRate(currency_pair="INR_GBP", rate=Decimal("106.0"))
    db.add(fx)
    await db.commit()

    # Should NOT call frankfurter since cache is fresh
    with patch("services.fx_service._fetch_from_frankfurter", new=AsyncMock()) as mock_fetch:
        rate = await get_rate("INR", "GBP", db)
        mock_fetch.assert_not_called()
    assert rate == Decimal("106.0")


@pytest.mark.asyncio
async def test_get_all_cached_rates_returns_list(db):
    fx = FxRate(currency_pair="INR_EUR", rate=Decimal("90.5"))
    db.add(fx)
    await db.commit()
    rates = await get_all_cached_rates(db)
    assert any(r.currency_pair == "INR_EUR" for r in rates)
