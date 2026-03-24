"""EximPe OPGSP improvements — UPI intent, KYB, FX lock, settlement tracking

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add upi_confirmed to transaction status enum
    op.execute("ALTER TYPE transaction_status_enum ADD VALUE IF NOT EXISTS 'upi_confirmed' AFTER 'inr_collected'")

    # Add new merchant columns
    op.add_column("merchants", sa.Column("business_type", sa.String(50), nullable=True))
    op.add_column("merchants", sa.Column("website_url", sa.String(500), nullable=True))
    op.add_column("merchants", sa.Column("incorporation_number", sa.String(100), nullable=True))
    op.add_column("merchants", sa.Column("kyb_status", sa.String(50), nullable=True, server_default="PENDING"))

    # Add new transaction columns — UPI intent
    op.add_column("transactions", sa.Column("upi_deep_link", sa.String(1000), nullable=True))
    op.add_column("transactions", sa.Column("upi_qr_payload", sa.String(1000), nullable=True))
    op.add_column("transactions", sa.Column("vpa", sa.String(100), nullable=True))
    op.add_column("transactions", sa.Column("upi_ref", sa.String(100), nullable=True))
    op.add_column("transactions", sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True))

    # OPGSP cap
    op.add_column("transactions", sa.Column("usd_equivalent", sa.Numeric(18, 4), nullable=True))
    op.add_column("transactions", sa.Column("opgsp_cap_applied", sa.Boolean(), nullable=True))

    # FX rate locking
    op.add_column("transactions", sa.Column("fx_rate_locked", sa.Numeric(18, 6), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_final", sa.Numeric(18, 6), nullable=True))

    # Collection and settlement tracking
    op.add_column("transactions", sa.Column("amount_inr_collected", sa.Numeric(18, 4), nullable=True))
    op.add_column("transactions", sa.Column("merchant_country", sa.String(10), nullable=True))
    op.add_column("transactions", sa.Column("opgsp_ref", sa.String(100), nullable=True))
    op.add_column("transactions", sa.Column("settlement_initiated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transactions", sa.Column("settlement_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove transaction columns
    op.drop_column("transactions", "settlement_completed_at")
    op.drop_column("transactions", "settlement_initiated_at")
    op.drop_column("transactions", "opgsp_ref")
    op.drop_column("transactions", "merchant_country")
    op.drop_column("transactions", "amount_inr_collected")
    op.drop_column("transactions", "fx_rate_final")
    op.drop_column("transactions", "fx_rate_expires_at")
    op.drop_column("transactions", "fx_rate_locked_at")
    op.drop_column("transactions", "fx_rate_locked")
    op.drop_column("transactions", "opgsp_cap_applied")
    op.drop_column("transactions", "usd_equivalent")
    op.drop_column("transactions", "payment_expires_at")
    op.drop_column("transactions", "upi_ref")
    op.drop_column("transactions", "vpa")
    op.drop_column("transactions", "upi_qr_payload")
    op.drop_column("transactions", "upi_deep_link")

    # Remove merchant columns
    op.drop_column("merchants", "kyb_status")
    op.drop_column("merchants", "incorporation_number")
    op.drop_column("merchants", "website_url")
    op.drop_column("merchants", "business_type")
    # Note: upi_confirmed enum value cannot be removed from PostgreSQL enum without recreating it
