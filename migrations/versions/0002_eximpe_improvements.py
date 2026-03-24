"""CrossBorderApp OPGSP improvements — UPI intent, KYB, FX lock, settlement tracking

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-24

Note: uses ADD COLUMN IF NOT EXISTS throughout so this migration is safe to
run against both fresh installs (columns already present from 0001) and
upgrades from an older version of 0001 that lacked these columns.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure upi_confirmed exists in the enum (idempotent)
    op.execute("ALTER TYPE transaction_status_enum ADD VALUE IF NOT EXISTS 'upi_confirmed' AFTER 'inr_collected'")

    # Ensure enum types exist (idempotent)
    op.execute("DO $$ BEGIN CREATE TYPE kyb_status_enum AS ENUM ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE business_type_enum AS ENUM ('ECOMMERCE', 'SAAS', 'MARKETPLACE', 'D2C'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    # Merchant columns
    op.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS kyb_status VARCHAR(50) NOT NULL DEFAULT 'PENDING'")
    op.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS business_type VARCHAR(50)")
    op.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS website_url VARCHAR(500)")
    op.execute("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS incorporation_number VARCHAR(100)")

    # Transaction columns — UPI intent
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS upi_deep_link VARCHAR(1000)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS upi_qr_payload VARCHAR(1000)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS vpa VARCHAR(100)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS upi_ref VARCHAR(100)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_expires_at TIMESTAMPTZ")

    # Transaction columns — OPGSP cap
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS usd_equivalent NUMERIC(18,4)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS opgsp_cap_applied BOOLEAN DEFAULT FALSE")

    # Transaction columns — FX rate locking
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fx_rate_locked NUMERIC(18,6)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fx_rate_locked_at TIMESTAMPTZ")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fx_rate_expires_at TIMESTAMPTZ")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fx_rate_final NUMERIC(18,6)")

    # Transaction columns — settlement tracking
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS amount_inr_collected NUMERIC(18,4)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_country VARCHAR(10)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS opgsp_ref VARCHAR(100)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS settlement_initiated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS settlement_completed_at TIMESTAMPTZ")


def downgrade() -> None:
    for col in [
        "settlement_completed_at", "settlement_initiated_at", "opgsp_ref",
        "merchant_country", "amount_inr_collected", "fx_rate_final",
        "fx_rate_expires_at", "fx_rate_locked_at", "fx_rate_locked",
        "opgsp_cap_applied", "usd_equivalent", "payment_expires_at",
        "upi_ref", "vpa", "upi_qr_payload", "upi_deep_link",
    ]:
        op.execute(f"ALTER TABLE transactions DROP COLUMN IF EXISTS {col}")

    for col in ["kyb_status", "incorporation_number", "website_url", "business_type"]:
        op.execute(f"ALTER TABLE merchants DROP COLUMN IF EXISTS {col}")
    # Note: upi_confirmed cannot be removed from a Postgres enum without recreating it
