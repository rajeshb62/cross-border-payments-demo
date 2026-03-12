"""Replace Circle with Coinbase Prime: rename beneficiary column.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename circle_wire_id → coinbase_counterparty_id on beneficiaries.
    # payout_order_id on transactions is already provider-agnostic — no change needed.
    op.alter_column("beneficiaries", "circle_wire_id", new_column_name="coinbase_counterparty_id")


def downgrade() -> None:
    op.alter_column("beneficiaries", "coinbase_counterparty_id", new_column_name="circle_wire_id")
