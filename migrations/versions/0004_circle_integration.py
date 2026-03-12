"""Replace TransFi with Circle: rename payout column, add circle_wire_id.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename transfi_order_id → payout_order_id on transactions
    op.drop_index("ix_transactions_transfi_order_id", table_name="transactions")
    op.alter_column("transactions", "transfi_order_id", new_column_name="payout_order_id")
    op.create_index("ix_transactions_payout_order_id", "transactions", ["payout_order_id"])

    # 2. Cache Circle wire account ID on beneficiaries (set once on first payout)
    op.add_column(
        "beneficiaries",
        sa.Column("circle_wire_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("beneficiaries", "circle_wire_id")
    op.drop_index("ix_transactions_payout_order_id", table_name="transactions")
    op.alter_column("transactions", "payout_order_id", new_column_name="transfi_order_id")
    op.create_index("ix_transactions_transfi_order_id", "transactions", ["transfi_order_id"])
