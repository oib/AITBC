"""Add optional deadline_height column on bounty_contract rows.

Revision ID: c7d9e1f3a5b7
Revises: b2c4d6e8f0a1
Create Date: 2026-11-21 00:00:00.000000+00:00

#2368: /rpc/bounty deploy accepts an optional deadline_height; expire_bounty
refuses while the chain head is below it. NULL keeps the legacy
expire-anytime semantics. Nullable with no default, so existing rows need
no backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d9e1f3a5b7"
down_revision: str | Sequence[str] | None = "b2c4d6e8f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "bounty_contract" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("bounty_contract")}
    if "deadline_height" not in existing:
        op.add_column("bounty_contract", sa.Column("deadline_height", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "bounty_contract" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("bounty_contract")}
    if "deadline_height" in existing:
        op.drop_column("bounty_contract", "deadline_height")
