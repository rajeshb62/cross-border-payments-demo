"""Add TransFi crypto-rails support: new status + order_id column.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the new enum value to the PostgreSQL type
    op.execute("ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'crypto_rails_pending'")

    # 2. Add transfi_order_id column
    op.add_column(
        "transactions",
        sa.Column("transfi_order_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_transactions_transfi_order_id", "transactions", ["transfi_order_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_transfi_order_id", table_name="transactions")
    op.drop_column("transactions", "transfi_order_id")
    # Note: PostgreSQL does not support removing enum values without recreating the type.
    # To fully downgrade, recreate the enum without 'crypto_rails_pending'.
