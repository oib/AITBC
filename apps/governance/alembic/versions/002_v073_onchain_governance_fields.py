"""v0.7.3 on-chain governance fields (chain_id, block_height, tx_hash)

Adds chain_id, block_height, and tx_hash columns to proposals and votes
tables for on-chain governance integration.

Revision ID: 002
Revises: 001
Create Date: 2026-06-29 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# V23-53: this migration is idempotent, but the guard has to be asked of the database
# rather than written into the SQL. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and
# `DROP COLUMN IF EXISTS` are PostgreSQL-only; SQLite rejects both outright with
# `near "EXISTS": syntax error`, and `apps/governance/alembic/env.py` defaults DB_TYPE
# to "sqlite". Production carries DB_TYPE=postgresql in its env file, so raw SQL passes
# there and fails everywhere else -- CI, a fresh checkout, anyone running alembic
# without sourcing the service env.
#
# The inspector answers the same question in a way every backend understands, so the
# migration stays re-runnable without becoming dialect-specific.

_COLUMNS = (
    ("chain_id", lambda: sa.Column("chain_id", sa.String(), nullable=False, server_default="ait-hub")),
    ("block_height", lambda: sa.Column("block_height", sa.Integer(), nullable=True)),
    ("tx_hash", lambda: sa.Column("tx_hash", sa.String(), nullable=True)),
)

_TABLES = (("proposals", "idx_proposals_chain_id"), ("votes", "idx_votes_chain_id"))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    for table, index_name in _TABLES:
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, build in _COLUMNS:
            if name not in existing:
                op.add_column(table, build())

        if index_name not in {index["name"] for index in inspector.get_indexes(table)}:
            op.create_index(index_name, table, ["chain_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    for table, index_name in reversed(_TABLES):
        if index_name in {index["name"] for index in inspector.get_indexes(table)}:
            op.drop_index(index_name, table_name=table)

        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, _ in reversed(_COLUMNS):
            if name in existing:
                op.drop_column(table, name)
