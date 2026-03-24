# DEMO SIMPLIFICATION: Fetches live rates from frankfurter.app (free, no auth).
#   Caches in Postgres FxRate table; refreshes if older than FX_CACHE_TTL_SECONDS.
# PRODUCTION TODO: Use a paid FX data provider (e.g. XE, Bloomberg, Wise FX API),
#   implement bid/ask spread, apply markup margin, add rate-lock with TTL for customers.

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import FXRateUnavailableError
from models.fx_rate import FxRate
from models.merchant import SettlementCurrency


# Active OPGSP settlement currencies (EUR and CNH removed at app layer)
SETTLEMENT_CURRENCIES = ["USD", "SGD", "AED", "GBP", "HKD"]

# Fallback mock rates when frankfurter.app is unavailable (~83.5 INR/USD)
MOCK_RATES = {
    "INR_USD": Decimal("0.011976"),   # ~83.5 INR/USD
    "INR_SGD": Decimal("0.016080"),
    "INR_AED": Decimal("0.044000"),
    "INR_GBP": Decimal("0.009500"),
    "INR_HKD": Decimal("0.093400"),
    "INR_EUR": Decimal("0.011050"),   # ~90.5 INR/EUR
    "INR_CNH": Decimal("0.086580"),   # ~11.55 INR/CNH
}


async def get_rate(from_currency: str, to_currency: str, db: AsyncSession) -> Decimal:
    """
    Return the INR→{to_currency} rate. Fetches fresh rate if cached value is stale.
    Rate is stored as: how many INR per 1 unit of to_currency (e.g. INR_USD = 83.5 means 1 USD = ₹83.5).
    """
    pair = f"{from_currency}_{to_currency}"
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.FX_CACHE_TTL_SECONDS)

    result = await db.execute(
        select(FxRate)
        .where(FxRate.currency_pair == pair)
        .where(FxRate.fetched_at >= cutoff)
        .order_by(desc(FxRate.fetched_at))
        .limit(1)
    )
    cached = result.scalar_one_or_none()
    if cached:
        return cached.rate

    # Cache miss — fetch from frankfurter.app
    rate = await _fetch_from_frankfurter(from_currency, to_currency)
    fx = FxRate(currency_pair=pair, rate=rate)
    db.add(fx)
    await db.commit()
    return rate


async def _fetch_from_frankfurter(from_currency: str, to_currency: str) -> Decimal:
    """
    Fetch live rate from frankfurter.app. Returns INR per 1 unit of to_currency.
    Falls back to MOCK_RATES if the API is unavailable.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.FRANKFURTER_API_URL}/latest",
                params={"from": from_currency, "to": to_currency},
            )
            resp.raise_for_status()
            data = resp.json()
            raw_rate = Decimal(str(data["rates"][to_currency]))
            # raw_rate = 1 INR in to_currency units; invert to get INR per 1 to_currency
            return (Decimal("1") / raw_rate).quantize(Decimal("0.000001"))
    except Exception:
        # Fall back to mock rates so tests and offline demos work
        pair = f"{from_currency}_{to_currency}"
        mock = MOCK_RATES.get(pair)
        if mock is not None:
            # mock stores the direct rate (1 INR = mock to_currency); invert for INR per unit
            return (Decimal("1") / mock).quantize(Decimal("0.000001"))
        raise FXRateUnavailableError(
            f"Failed to fetch FX rate {from_currency}→{to_currency} and no mock available"
        )


async def convert(inr_amount: Decimal, settlement_currency: str, db: AsyncSession) -> tuple[Decimal, Decimal]:
    """
    Convert INR amount to settlement currency.
    Returns (rate, settlement_amount_before_fee).
    rate = INR per 1 settlement currency unit.
    """
    rate = await get_rate("INR", settlement_currency, db)
    settlement_amount = (inr_amount / rate).quantize(Decimal("0.0001"))
    return rate, settlement_amount


async def refresh_all_rates(db: AsyncSession) -> None:
    """Fetch and cache rates for all 5 active settlement currencies from INR."""
    for currency in SETTLEMENT_CURRENCIES:
        try:
            rate = await _fetch_from_frankfurter("INR", currency)
            fx = FxRate(currency_pair=f"INR_{currency}", rate=rate)
            db.add(fx)
        except FXRateUnavailableError:
            pass  # Log but don't fail the whole batch
    await db.commit()


async def get_all_cached_rates(db: AsyncSession) -> list[FxRate]:
    """Return most recent cached rate for each settlement currency."""
    rates = []
    for currency in SETTLEMENT_CURRENCIES:
        pair = f"INR_{currency}"
        result = await db.execute(
            select(FxRate)
            .where(FxRate.currency_pair == pair)
            .order_by(desc(FxRate.fetched_at))
            .limit(1)
        )
        fx = result.scalar_one_or_none()
        if fx:
            rates.append(fx)
    return rates
