"""Add chain_id and wallet_address to miners table.

Revision ID: 21da5cfdcc95
Revises: e5d4f8a9b0c1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "21da5cfdcc95"
down_revision = "e5d4f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("miners")}
    if "chain_id" not in cols:
        op.add_column("miners", sa.Column("chain_id", sa.String(64), nullable=False, server_default="ait-hub"))
    if "wallet_address" not in cols:
        op.add_column("miners", sa.Column("wallet_address", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("miners", "wallet_address")
    op.drop_column("miners", "chain_id")
