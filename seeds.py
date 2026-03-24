"""
Demo seed data for EximPe.
Creates 3 merchants (Acme SaaS, Berlin Marketplace, Singapore Retailer)
with virtual accounts and 5 sample transactions.

Usage:
    python seeds.py
"""
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from core.database import Base
from models.merchant import Merchant, MerchantStatus, SettlementCurrency, VirtualAccount
from models.transaction import Transaction, TransactionStatus, PaymentMethod
import models.fx_rate        # noqa: ensure metadata registered
import models.reconciliation  # noqa: ensure metadata registered


MERCHANTS = [
    {
        "name": "Acme SaaS",
        "email": "billing@acmesaas.com",
        "country": "US",
        "settlement_currency": SettlementCurrency.USD,
        "settlement_account_details": {
            "bank_name": "Chase Bank",
            "account_number": "987654321",
            "swift": "CHASUS33",
        },
        "purpose_code": "P0802",
    },
    {
        "name": "Berlin Marketplace",
        "email": "finance@berlinmarket.de",
        "country": "DE",
        "settlement_currency": SettlementCurrency.EUR,
        "settlement_account_details": {
            "bank_name": "Deutsche Bank",
            "account_number": "DE89370400440532013000",
            "swift": "DEUTDEDB",
        },
        "purpose_code": "P0802",
    },
    {
        "name": "Singapore Retailer",
        "email": "accounts@sgshoppe.sg",
        "country": "SG",
        "settlement_currency": SettlementCurrency.SGD,
        "settlement_account_details": {
            "bank_name": "DBS Bank",
            "account_number": "0011234567",
            "swift": "DBSSSGSG",
        },
        "purpose_code": "P1007",
    },
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with session_factory() as db:
        merchant_ids = []

        for m_data in MERCHANTS:
            merchant = Merchant(
                name=m_data["name"],
                email=m_data["email"],
                country=m_data["country"],
                settlement_currency=m_data["settlement_currency"],
                settlement_account_details=m_data["settlement_account_details"],
                status=MerchantStatus.active,
            )
            db.add(merchant)
            await db.flush()

            va = VirtualAccount(
                merchant_id=merchant.id,
                inr_account_number=str(hash(m_data["email"]) % 10**12).zfill(12),
                ifsc_code="EXIMPE0001",
                is_active=True,
            )
            db.add(va)
            await db.flush()

            merchant_ids.append((merchant.id, va.id, m_data["settlement_currency"], m_data["purpose_code"]))

        await db.commit()

        # 5 sample transactions across the 3 merchants
        sample_txns = [
            (merchant_ids[0], Decimal("50000"), PaymentMethod.upi, TransactionStatus.settled),
            (merchant_ids[0], Decimal("120000"), PaymentMethod.netbanking, TransactionStatus.inr_collected),
            (merchant_ids[1], Decimal("75000"), PaymentMethod.card, TransactionStatus.fx_converted),
            (merchant_ids[2], Decimal("30000"), PaymentMethod.upi, TransactionStatus.initiated),
            (merchant_ids[2], Decimal("800000"), PaymentMethod.netbanking, TransactionStatus.settled),
        ]

        for (m_id, va_id, currency, purpose_code), amount, method, status in sample_txns:
            tx = Transaction(
                merchant_id=m_id,
                virtual_account_id=va_id,
                payment_method=method,
                inr_amount=amount,
                settlement_currency=currency,
                fee_inr=(amount * Decimal("0.015")).quantize(Decimal("0.01")),
                tcs_applicable=(purpose_code == "P1007"),
                tcs_rate=Decimal("0.005") if purpose_code == "P1007" else Decimal("0"),
                purpose_code=purpose_code,
                status=status,
            )
            if status in (TransactionStatus.settled, TransactionStatus.fx_converted):
                tx.fx_rate = Decimal("83.50")
                net = ((amount - tx.fee_inr) / Decimal("83.50")).quantize(Decimal("0.0001"))
                tx.settlement_amount = net
            db.add(tx)

        await db.commit()
        print("Seed data created successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
