"""EximPe initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums
    op.execute("CREATE TYPE settlement_currency_enum AS ENUM ('USD', 'EUR', 'GBP', 'SGD', 'AED', 'HKD', 'CNH')")
    op.execute("CREATE TYPE merchant_status_enum AS ENUM ('pending_kyc', 'active', 'suspended')")
    op.execute("CREATE TYPE payment_method_enum AS ENUM ('upi', 'netbanking', 'card')")
    op.execute("CREATE TYPE transaction_status_enum AS ENUM ('initiated', 'inr_collected', 'fx_converted', 'settled', 'failed')")
    op.execute("CREATE TYPE reconciliation_status_enum AS ENUM ('matched', 'mismatch', 'pending')")

    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("settlement_currency", sa.Enum("USD", "EUR", "GBP", "SGD", "AED", "HKD", "CNH", name="settlement_currency_enum", create_type=False), nullable=False),
        sa.Column("settlement_account_details", postgresql.JSON(), nullable=False),
        sa.Column("status", sa.Enum("pending_kyc", "active", "suspended", name="merchant_status_enum", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "virtual_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("inr_account_number", sa.String(20), nullable=False, unique=True),
        sa.Column("ifsc_code", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("virtual_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("virtual_accounts.id"), nullable=False),
        sa.Column("payment_method", sa.Enum("upi", "netbanking", "card", name="payment_method_enum", create_type=False), nullable=False),
        sa.Column("inr_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("fx_rate", sa.Numeric(18, 6), nullable=True),
        sa.Column("settlement_currency", sa.Enum("USD", "EUR", "GBP", "SGD", "AED", "HKD", "CNH", name="settlement_currency_enum", create_type=False), nullable=False),
        sa.Column("settlement_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("fee_inr", sa.Numeric(18, 4), nullable=True),
        sa.Column("tcs_applicable", sa.Boolean(), nullable=False, default=False),
        sa.Column("tcs_rate", sa.Numeric(6, 4), nullable=False, default=0),
        sa.Column("purpose_code", sa.String(20), nullable=False),
        sa.Column("status", sa.Enum("initiated", "inr_collected", "fx_converted", "settled", "failed", name="transaction_status_enum", create_type=False), nullable=False),
        sa.Column("payer_upi_id", sa.String(100), nullable=True),
        sa.Column("payer_bank", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index("ix_transactions_merchant_id", "transactions", ["merchant_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])

    op.create_table(
        "fx_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("currency_pair", sa.String(20), nullable=False, index=True),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "reconciliation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("expected_settlement_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("actual_settlement_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.Enum("matched", "mismatch", "pending", name="reconciliation_status_enum", create_type=False), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_logs")
    op.drop_table("fx_rates")
    op.drop_table("transactions")
    op.drop_table("virtual_accounts")
    op.drop_table("merchants")
    op.execute("DROP TYPE IF EXISTS reconciliation_status_enum")
    op.execute("DROP TYPE IF EXISTS transaction_status_enum")
    op.execute("DROP TYPE IF EXISTS payment_method_enum")
    op.execute("DROP TYPE IF EXISTS merchant_status_enum")
    op.execute("DROP TYPE IF EXISTS settlement_currency_enum")
