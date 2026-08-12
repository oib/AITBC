"""V23-18: record voting_ends_block on proposals

The execution timelock previously ran from ``block_height`` (proposal creation),
which makes it overlap the voting period instead of following it. This column
records the block at which voting closes so the timelock can run from there.

Existing rows are left NULL. That is deliberate: a proposal created before this
migration has no recorded voting-end block, and the service refuses to execute a
proposal whose timelock it cannot verify rather than guessing one. Backfilling
from ``block_height`` would manufacture exactly the evidence the check exists to
demand.

Revision ID: 003
Revises: 002
Create Date: 2026-08-09 19:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(name: str) -> bool:
    # V23-53: same inspector guard as 002. Making 002 re-runnable and leaving this one
    # alone would have moved the abort one revision later without changing the outcome --
    # `alembic upgrade head` still stops, just at 003 instead of 002.
    return name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("proposals")}


def upgrade() -> None:
    if not _has_column("voting_ends_block"):
        op.add_column("proposals", sa.Column("voting_ends_block", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _has_column("voting_ends_block"):
        op.drop_column("proposals", "voting_ends_block")
