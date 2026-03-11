"""Tests for Beneficiary CRUD and transaction linkage."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.beneficiary import Beneficiary
from models.transaction import Transaction
from services.transaction import create_transaction


async def _make_beneficiary(db, user_id: str = "user_ben_001") -> Beneficiary:
    b = Beneficiary(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name="John Doe",
        bank_name="Chase Bank",
        account_number="123456789",
        swift_bic="CHASUS33",
        routing_number="021000021",
        country_code="US",
        currency="USD",
    )
    db.add(b)
    await db.flush()
    return b


@pytest.mark.asyncio
async def test_create_beneficiary(db):
    b = await _make_beneficiary(db)
    await db.commit()
    assert b.id is not None
    assert b.swift_bic == "CHASUS33"
    assert b.country_code == "US"
    assert b.currency == "USD"


@pytest.mark.asyncio
async def test_get_beneficiary_by_id(db):
    b = await _make_beneficiary(db, user_id=f"user_{uuid.uuid4()}")
    await db.commit()

    result = await db.execute(select(Beneficiary).where(Beneficiary.id == b.id))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.full_name == "John Doe"
    assert fetched.bank_name == "Chase Bank"


@pytest.mark.asyncio
async def test_list_beneficiaries_by_user(db):
    uid = f"user_list_{uuid.uuid4()}"
    await _make_beneficiary(db, user_id=uid)
    await _make_beneficiary(db, user_id=uid)
    await db.commit()

    result = await db.execute(select(Beneficiary).where(Beneficiary.user_id == uid))
    rows = result.scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_create_transaction_with_beneficiary(db):
    b = await _make_beneficiary(db, user_id=f"user_{uuid.uuid4()}")
    await db.flush()

    tx = await create_transaction(
        db=db,
        user_id=b.user_id,
        amount_inr=Decimal("835000"),
        purpose_code="P0001",
        idempotency_key=str(uuid.uuid4()),
        beneficiary_id=b.id,
    )
    await db.commit()

    assert tx.beneficiary_id == b.id


@pytest.mark.asyncio
async def test_create_transaction_without_beneficiary(db):
    tx = await create_transaction(
        db=db,
        user_id=f"user_{uuid.uuid4()}",
        amount_inr=Decimal("500000"),
        purpose_code="P0001",
        idempotency_key=str(uuid.uuid4()),
    )
    await db.commit()
    assert tx.beneficiary_id is None


@pytest.mark.asyncio
async def test_beneficiary_fk_persisted_on_transaction(db):
    b = await _make_beneficiary(db, user_id=f"user_{uuid.uuid4()}")
    await db.flush()

    tx = await create_transaction(
        db=db,
        user_id=b.user_id,
        amount_inr=Decimal("200000"),
        purpose_code="P0001",
        idempotency_key=str(uuid.uuid4()),
        beneficiary_id=b.id,
    )
    await db.commit()

    result = await db.execute(select(Transaction).where(Transaction.id == tx.id))
    fetched = result.scalar_one()
    assert str(fetched.beneficiary_id) == str(b.id)
