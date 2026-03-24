"""Shared test fixtures using SQLite (in-memory) + fakeredis."""
import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.database import Base

# Import all models so Base.metadata is populated
import models.merchant       # noqa: F401
import models.transaction    # noqa: F401
import models.fx_rate        # noqa: F401
import models.reconciliation # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis as fake_aioredis
    return fake_aioredis.FakeRedis(decode_responses=True)
