"""One vote per voter per proposal, enforced at the DB level (#1610)

``GovernanceService.create_vote`` guards duplicates with a check-then-insert
scan, but ``votes`` had no unique constraint on ``(proposal_id, voter_id)``,
so two concurrent votes from the same voter both landed and stacked weight
(#1091 regression under concurrency).

The index keys on ``lower(voter_id)`` because the service's duplicate check
is case-insensitive — a plain ``UNIQUE(proposal_id, voter_id)`` would let
``"Voter"``/``"voter"`` racers through. Functional indexes are supported by
both SQLite (>=3.9) and PostgreSQL.

Before creating the index, pre-existing duplicates (if any) are collapsed to
the earliest row per ``(proposal_id, lower(voter_id))`` — the same rows the
constraint now forbids. Proposal vote counters are not recomputed; they were
already inflated by those duplicates and the service treats them as advisory
tallies recomputed at close time where applicable.

Revision ID: 006
Revises: 005
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "uq_votes_proposal_voter_ci"


def _has_index(name: str) -> bool:
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("votes")}


def upgrade() -> None:
    if not _has_index(_INDEX_NAME):
        # Collapse rows the new constraint would reject, keeping the earliest
        # vote per (proposal_id, case-insensitive voter_id).
        op.execute(
            sa.text(
                """
                DELETE FROM votes
                WHERE vote_id NOT IN (
                    SELECT vote_id FROM (
                        SELECT vote_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY proposal_id, lower(voter_id)
                                   ORDER BY created_at ASC, vote_id ASC
                               ) AS rn
                        FROM votes
                    ) AS ranked
                    WHERE rn = 1
                )
                """
            )
        )
        op.create_index(
            _INDEX_NAME,
            "votes",
            ["proposal_id", sa.func.lower(sa.column("voter_id"))],
            unique=True,
        )


def downgrade() -> None:
    if _has_index(_INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name="votes")
