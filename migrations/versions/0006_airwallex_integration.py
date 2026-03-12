"""Replace Coinbase with Airwallex: rename status enum value + beneficiary column.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-12
"""
from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename the status enum value (PostgreSQL 10+)
    #    crypto_rails_pending → payout_pending
    #    This reflects that delivery is now via fiat LOCAL rails, not crypto.
    op.execute(
        "ALTER TYPE transaction_status RENAME VALUE 'crypto_rails_pending' TO 'payout_pending'"
    )

    # 2. Rename the beneficiary column
    op.alter_column(
        "beneficiaries", "coinbase_counterparty_id",
        new_column_name="airwallex_beneficiary_id",
    )


def downgrade() -> None:
    op.alter_column(
        "beneficiaries", "airwallex_beneficiary_id",
        new_column_name="coinbase_counterparty_id",
    )
    op.execute(
        "ALTER TYPE transaction_status RENAME VALUE 'payout_pending' TO 'crypto_rails_pending'"
    )
