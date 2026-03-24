"""EximPe initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enum types ────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE settlement_currency_enum AS ENUM ('USD', 'EUR', 'GBP', 'SGD', 'AED', 'HKD', 'CNH');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE merchant_status_enum AS ENUM ('pending_kyc', 'active', 'suspended');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE kyb_status_enum AS ENUM ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE business_type_enum AS ENUM ('ECOMMERCE', 'SAAS', 'MARKETPLACE', 'D2C');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE payment_method_enum AS ENUM ('upi', 'netbanking', 'card');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_status_enum AS ENUM (
                'initiated', 'inr_collected', 'upi_confirmed', 'fx_converted', 'settled', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE reconciliation_status_enum AS ENUM ('matched', 'mismatch', 'pending');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)

    # ── Tables ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            country VARCHAR(10) NOT NULL,
            settlement_currency settlement_currency_enum NOT NULL,
            settlement_account_details JSON NOT NULL DEFAULT '{}',
            status merchant_status_enum NOT NULL DEFAULT 'pending_kyc',
            kyb_status kyb_status_enum NOT NULL DEFAULT 'PENDING',
            business_type business_type_enum,
            website_url VARCHAR(500),
            incorporation_number VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS virtual_accounts (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            inr_account_number VARCHAR(20) NOT NULL UNIQUE,
            ifsc_code VARCHAR(20) NOT NULL DEFAULT 'EXIMPE0001',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            virtual_account_id UUID NOT NULL REFERENCES virtual_accounts(id),
            payment_method payment_method_enum NOT NULL,
            inr_amount NUMERIC(18,4) NOT NULL,
            fx_rate NUMERIC(18,6),
            settlement_currency settlement_currency_enum NOT NULL,
            settlement_amount NUMERIC(18,4),
            fee_inr NUMERIC(18,4),
            purpose_code VARCHAR(20) NOT NULL,
            status transaction_status_enum NOT NULL DEFAULT 'initiated',
            payer_upi_id VARCHAR(100),
            payer_bank VARCHAR(100),
            upi_deep_link VARCHAR(1000),
            upi_qr_payload VARCHAR(1000),
            vpa VARCHAR(100),
            upi_ref VARCHAR(100),
            payment_expires_at TIMESTAMPTZ,
            usd_equivalent NUMERIC(18,4),
            opgsp_cap_applied BOOLEAN DEFAULT FALSE,
            fx_rate_locked NUMERIC(18,6),
            fx_rate_locked_at TIMESTAMPTZ,
            fx_rate_expires_at TIMESTAMPTZ,
            fx_rate_final NUMERIC(18,6),
            amount_inr_collected NUMERIC(18,4),
            merchant_country VARCHAR(10),
            opgsp_ref VARCHAR(100),
            settlement_initiated_at TIMESTAMPTZ,
            settlement_completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_merchant_id ON transactions(merchant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_status ON transactions(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS fx_rates (
            id UUID PRIMARY KEY,
            currency_pair VARCHAR(20) NOT NULL,
            rate NUMERIC(18,6) NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fx_rates_currency_pair ON fx_rates(currency_pair)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_logs (
            id UUID PRIMARY KEY,
            transaction_id UUID NOT NULL REFERENCES transactions(id),
            expected_settlement_amount NUMERIC(18,4) NOT NULL,
            actual_settlement_amount NUMERIC(18,4) NOT NULL,
            status reconciliation_status_enum NOT NULL DEFAULT 'pending',
            checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reconciliation_logs")
    op.execute("DROP TABLE IF EXISTS fx_rates")
    op.execute("DROP TABLE IF EXISTS transactions")
    op.execute("DROP TABLE IF EXISTS virtual_accounts")
    op.execute("DROP TABLE IF EXISTS merchants")
    op.execute("DROP TYPE IF EXISTS reconciliation_status_enum")
    op.execute("DROP TYPE IF EXISTS transaction_status_enum")
    op.execute("DROP TYPE IF EXISTS payment_method_enum")
    op.execute("DROP TYPE IF EXISTS business_type_enum")
    op.execute("DROP TYPE IF EXISTS kyb_status_enum")
    op.execute("DROP TYPE IF EXISTS merchant_status_enum")
    op.execute("DROP TYPE IF EXISTS settlement_currency_enum")
