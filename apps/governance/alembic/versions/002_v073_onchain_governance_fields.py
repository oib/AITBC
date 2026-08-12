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


def upgrade() -> None:
    # Add on-chain governance fields to proposals (idempotent)
    op.execute(sa.text("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS chain_id VARCHAR NOT NULL DEFAULT 'ait-hub'"))
    op.execute(sa.text("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS block_height INTEGER"))
    op.execute(sa.text("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS tx_hash VARCHAR"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_proposals_chain_id ON proposals (chain_id)"))

    # Add on-chain governance fields to votes (idempotent)
    op.execute(sa.text("ALTER TABLE votes ADD COLUMN IF NOT EXISTS chain_id VARCHAR NOT NULL DEFAULT 'ait-hub'"))
    op.execute(sa.text("ALTER TABLE votes ADD COLUMN IF NOT EXISTS block_height INTEGER"))
    op.execute(sa.text("ALTER TABLE votes ADD COLUMN IF NOT EXISTS tx_hash VARCHAR"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_votes_chain_id ON votes (chain_id)"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_votes_chain_id"))
    op.execute(sa.text("ALTER TABLE votes DROP COLUMN IF EXISTS tx_hash"))
    op.execute(sa.text("ALTER TABLE votes DROP COLUMN IF EXISTS block_height"))
    op.execute(sa.text("ALTER TABLE votes DROP COLUMN IF EXISTS chain_id"))

    op.execute(sa.text("DROP INDEX IF EXISTS idx_proposals_chain_id"))
    op.execute(sa.text("ALTER TABLE proposals DROP COLUMN IF EXISTS tx_hash"))
    op.execute(sa.text("ALTER TABLE proposals DROP COLUMN IF EXISTS block_height"))
    op.execute(sa.text("ALTER TABLE proposals DROP COLUMN IF EXISTS chain_id"))
