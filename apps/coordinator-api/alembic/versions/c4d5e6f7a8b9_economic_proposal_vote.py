"""add economic_proposal_vote table (#2494)

One vote per voter per economic proposal: the tallies on
``economic_parameter_proposal`` are snapshots that cannot express the
one-vote-per-voter rule, so votes are now recorded per (proposal, voter)
with a unique constraint. ``voting_power`` snapshots the caller's
effective power at cast time.

Revision ID: c4d5e6f7a8b9
Revises: b2375tee0drop
Create Date: 2026-11-22

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "b2375tee0drop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the economic_proposal_vote table."""
    op.create_table(
        "economic_proposal_vote",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=32), nullable=False),
        sa.Column("voter_id", sa.String(length=255), nullable=False),
        sa.Column("vote", sa.String(length=10), nullable=False),
        sa.Column("voting_power", sa.Float(), nullable=False, server_default=sa.text("'0.0'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "voter_id", name="uq_economic_proposal_vote"),
    )
    op.create_index("ix_economic_proposal_vote_proposal_id", "economic_proposal_vote", ["proposal_id"])
    op.create_index("ix_economic_proposal_vote_voter_id", "economic_proposal_vote", ["voter_id"])


def downgrade() -> None:
    """Drop the economic_proposal_vote table."""
    op.drop_index("ix_economic_proposal_vote_voter_id", table_name="economic_proposal_vote")
    op.drop_index("ix_economic_proposal_vote_proposal_id", table_name="economic_proposal_vote")
    op.drop_table("economic_proposal_vote")
