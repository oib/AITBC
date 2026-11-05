"""Persist the signed-write replay set (#1132)

``_seen_signatures`` in ``governance_service.main`` was a process-local
dict, so a restart emptied it and a captured signed stake/delegate body
could be replayed inside the 300 s freshness window. ``used_signatures``
makes the consumed-signature check durable; ``expires_at`` carries the
same TTL the dict entries did.

Revision ID: 005
Revises: 004
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("used_signatures"):
        return
    op.create_table(
        "used_signatures",
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("signature"),
    )


def downgrade() -> None:
    if _has_table("used_signatures"):
        op.drop_table("used_signatures")
