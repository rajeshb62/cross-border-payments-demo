"""Tests for transaction state machine and idempotency."""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from core.exceptions import InvalidStateMachineTransitionError
from models.transaction import TransactionStatus
from services.transaction import create_transaction, execute_transaction


@pytest.mark.asyncio
async def test_create_transaction_returns_initiated(db):
    tx = await create_transaction(
        db=db,
        user_id="user_001",
        amount_inr=Decimal("835000"),
        purpose_code="P0001",
        idempotency_key=str(uuid.uuid4()),
    )
    await db.commit()
    assert tx.status == TransactionStatus.INITIATED
    assert tx.amount_inr == Decimal("835000")


@pytest.mark.asyncio
async def test_idempotency_returns_existing_transaction(db):
    key = str(uuid.uuid4())
    tx1 = await create_transaction(
        db=db,
        user_id="user_001",
        amount_inr=Decimal("100000"),
        purpose_code="P0001",
        idempotency_key=key,
    )
    await db.commit()

    tx2 = await create_transaction(
        db=db,
        user_id="user_001",
        amount_inr=Decimal("100000"),
        purpose_code="P0001",
        idempotency_key=key,
    )
    assert str(tx1.id) == str(tx2.id)


@pytest.mark.asyncio
async def test_full_state_machine_happy_path(db, fake_redis):
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        tx = await create_transaction(
            db=db,
            user_id="user_happy",
            amount_inr=Decimal("835000"),
            purpose_code="P0001",
            idempotency_key=str(uuid.uuid4()),
        )
        await db.commit()

        tx = await execute_transaction(db, str(tx.id))
        await db.commit()

    assert tx.status == TransactionStatus.SETTLED
    assert tx.amount_usd is not None
    assert tx.exchange_rate is not None
    assert tx.fx_reference_id is not None


@pytest.mark.asyncio
async def test_state_machine_invalid_transition(db, fake_redis):
    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        tx = await create_transaction(
            db=db,
            user_id="user_002",
            amount_inr=Decimal("835000"),
            purpose_code="P0001",
            idempotency_key=str(uuid.uuid4()),
        )
        await db.commit()
        tx = await execute_transaction(db, str(tx.id))
        await db.commit()

    # Already settled — any retry should raise
    with pytest.raises(Exception):
        with patch("services.fx_rate._get_redis", return_value=fake_redis):
            await execute_transaction(db, str(tx.id))


@pytest.mark.asyncio
async def test_transaction_fails_on_lrs_exceeded(db, fake_redis):
    """Transaction exceeding LRS should fail with LRSLimitExceededError."""
    from core.exceptions import LRSLimitExceededError

    with patch("services.fx_rate._get_redis", return_value=fake_redis):
        # First big transaction — use nearly full limit
        tx1 = await create_transaction(
            db=db,
            user_id="user_lrs_test",
            amount_inr=Decimal("20875000"),  # ~$250K
            purpose_code="P0001",
            idempotency_key=str(uuid.uuid4()),
        )
        await db.commit()
        await execute_transaction(db, str(tx1.id))
        await db.commit()

        # Second transaction should breach LRS
        tx2 = await create_transaction(
            db=db,
            user_id="user_lrs_test",
            amount_inr=Decimal("835000"),  # another ~$10K — should fail
            purpose_code="P0001",
            idempotency_key=str(uuid.uuid4()),
        )
        await db.commit()

        with pytest.raises(LRSLimitExceededError):
            await execute_transaction(db, str(tx2.id))
