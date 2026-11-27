"""Record the voting address on each vote (#3062)

Close-time backing re-verification needs to know WHICH on-chain address a
vote's weight was computed from; ``voter_id`` is a profile id that need not
be an address. Nullable — pre-existing rows fall back to ``voter_id``.

Revision ID: 007
Revises: 006
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | Sequence[str] | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("votes", "voter_address"):
        op.add_column("votes", sa.Column("voter_address", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("votes", "voter_address"):
        op.drop_column("votes", "voter_address")
