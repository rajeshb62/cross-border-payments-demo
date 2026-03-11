"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""DO $$ BEGIN CREATE TYPE transaction_status AS ENUM (
        'initiated','rate_locked','compliance_check','funds_debited',
        'fx_executed','funds_credited','settled','failed'
    ); EXCEPTION WHEN duplicate_object THEN null; END $$""")

    op.execute("""DO $$ BEGIN CREATE TYPE account_type AS ENUM (
        'customer_inr','fx_account','customer_usd','fee','tcs'
    ); EXCEPTION WHEN duplicate_object THEN null; END $$""")

    op.execute("""DO $$ BEGIN CREATE TYPE entry_type AS ENUM (
        'debit','credit'
    ); EXCEPTION WHEN duplicate_object THEN null; END $$""")

    op.execute("""DO $$ BEGIN CREATE TYPE kyc_status AS ENUM (
        'pending','verified','rejected','expired'
    ); EXCEPTION WHEN duplicate_object THEN null; END $$""")

    op.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id UUID PRIMARY KEY,
        idempotency_key VARCHAR(255) NOT NULL UNIQUE,
        user_id VARCHAR(255) NOT NULL,
        amount_inr NUMERIC(18,4) NOT NULL,
        amount_usd NUMERIC(18,4),
        exchange_rate NUMERIC(10,4),
        purpose_code VARCHAR(10) NOT NULL,
        purpose_description VARCHAR(255),
        is_education_loan VARCHAR(5) NOT NULL DEFAULT 'false',
        status transaction_status NOT NULL,
        tcs_amount NUMERIC(18,4),
        rate_lock_expires_at TIMESTAMPTZ,
        fx_reference_id VARCHAR(255),
        failure_reason TEXT,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_user_id ON transactions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_status ON transactions(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_idempotency_key ON transactions(idempotency_key)")

    op.execute("""CREATE TABLE IF NOT EXISTS transaction_events (
        id UUID PRIMARY KEY,
        transaction_id UUID NOT NULL REFERENCES transactions(id),
        from_status transaction_status,
        to_status transaction_status NOT NULL,
        note TEXT,
        created_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_transaction_events_transaction_id ON transaction_events(transaction_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS ledger_entries (
        id UUID PRIMARY KEY,
        transaction_id UUID NOT NULL REFERENCES transactions(id),
        account_type account_type NOT NULL,
        entry_type entry_type NOT NULL,
        currency VARCHAR(3) NOT NULL,
        amount NUMERIC(18,4) NOT NULL,
        description VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_ledger_entries_transaction_id ON ledger_entries(transaction_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS lrs_records (
        id UUID PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        financial_year VARCHAR(9) NOT NULL,
        utilized_usd NUMERIC(18,4) NOT NULL DEFAULT 0,
        limit_usd NUMERIC(18,4) NOT NULL DEFAULT 250000,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_lrs_records_user_id ON lrs_records(user_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS kyc_documents (
        id UUID PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        document_type VARCHAR(50) NOT NULL,
        document_number VARCHAR(100) NOT NULL,
        status kyc_status NOT NULL,
        verified_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_kyc_documents_user_id ON kyc_documents(user_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS tcs_records (
        id UUID PRIMARY KEY,
        transaction_id UUID NOT NULL REFERENCES transactions(id),
        user_id VARCHAR(255) NOT NULL,
        purpose_code VARCHAR(10) NOT NULL,
        tcs_rate NUMERIC(5,4) NOT NULL,
        taxable_amount_inr NUMERIC(18,4) NOT NULL,
        tcs_amount_inr NUMERIC(18,4) NOT NULL,
        financial_year VARCHAR(9) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_tcs_records_transaction_id ON tcs_records(transaction_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tcs_records_user_id ON tcs_records(user_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS fx_rates (
        id UUID PRIMARY KEY,
        from_currency VARCHAR(3) NOT NULL,
        to_currency VARCHAR(3) NOT NULL,
        rate NUMERIC(10,6) NOT NULL,
        source VARCHAR(50) NOT NULL DEFAULT 'wise_stub',
        fetched_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("""CREATE TABLE IF NOT EXISTS rate_locks (
        id UUID PRIMARY KEY,
        transaction_id VARCHAR(255) NOT NULL UNIQUE,
        from_currency VARCHAR(3) NOT NULL,
        to_currency VARCHAR(3) NOT NULL,
        locked_rate NUMERIC(10,6) NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS ix_rate_locks_transaction_id ON rate_locks(transaction_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rate_locks")
    op.execute("DROP TABLE IF EXISTS fx_rates")
    op.execute("DROP TABLE IF EXISTS tcs_records")
    op.execute("DROP TABLE IF EXISTS kyc_documents")
    op.execute("DROP TABLE IF EXISTS lrs_records")
    op.execute("DROP TABLE IF EXISTS ledger_entries")
    op.execute("DROP TABLE IF EXISTS transaction_events")
    op.execute("DROP TABLE IF EXISTS transactions")
    op.execute("DROP TYPE IF EXISTS kyc_status")
    op.execute("DROP TYPE IF EXISTS entry_type")
    op.execute("DROP TYPE IF EXISTS account_type")
    op.execute("DROP TYPE IF EXISTS transaction_status")
