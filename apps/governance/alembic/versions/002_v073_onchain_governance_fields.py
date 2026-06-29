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
    # Add on-chain governance fields to proposals
    op.add_column("proposals", sa.Column("chain_id", sa.String(), nullable=False, server_default="ait-hub"))
    op.add_column("proposals", sa.Column("block_height", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("tx_hash", sa.String(), nullable=True))
    op.create_index("idx_proposals_chain_id", "proposals", ["chain_id"])

    # Add on-chain governance fields to votes
    op.add_column("votes", sa.Column("chain_id", sa.String(), nullable=False, server_default="ait-hub"))
    op.add_column("votes", sa.Column("block_height", sa.Integer(), nullable=True))
    op.add_column("votes", sa.Column("tx_hash", sa.String(), nullable=True))
    op.create_index("idx_votes_chain_id", "votes", ["chain_id"])


def downgrade() -> None:
    op.drop_index("idx_votes_chain_id", table_name="votes")
    op.drop_column("votes", "tx_hash")
    op.drop_column("votes", "block_height")
    op.drop_column("votes", "chain_id")

    op.drop_index("idx_proposals_chain_id", table_name="proposals")
    op.drop_column("proposals", "tx_hash")
    op.drop_column("proposals", "block_height")
    op.drop_column("proposals", "chain_id")
