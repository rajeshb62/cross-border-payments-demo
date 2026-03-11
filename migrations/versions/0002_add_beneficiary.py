"""Add beneficiary table and FK on transactions

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS beneficiaries (
        id             UUID PRIMARY KEY,
        user_id        VARCHAR(255) NOT NULL,
        full_name      VARCHAR(255) NOT NULL,
        bank_name      VARCHAR(255) NOT NULL,
        account_number VARCHAR(100) NOT NULL,
        swift_bic      VARCHAR(11)  NOT NULL,
        routing_number VARCHAR(50),
        country_code   VARCHAR(2)   NOT NULL,
        currency       VARCHAR(3)   NOT NULL,
        created_at     TIMESTAMPTZ  DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_beneficiaries_user_id ON beneficiaries(user_id)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS beneficiary_id UUID REFERENCES beneficiaries(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_beneficiary_id ON transactions(beneficiary_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transactions_beneficiary_id")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS beneficiary_id")
    op.execute("DROP TABLE IF EXISTS beneficiaries")
