"""Baseline: create every gpu_metadata table on an empty database.

Both existing revisions are alteration-only — ``b8f3a2c91d04`` converts
money columns and ``4d6e9c8a1b52`` adds ``chain_id`` — so ``alembic
upgrade head`` on a fresh database produced exactly one table
(``alembic_version``) and left ``init_db``/``create_all`` to build the
real schema untracked. This baseline makes the migration graph
self-sufficient: every table ``gpu_metadata`` knows about is created
here, ``checkfirst`` so already-deployed databases (whose tables exist)
pass through untouched.

Later revisions stay as they are: the money-column conversion finds
columns already ``Numeric(20, 8)`` on a fresh database and the chain_id
guard sees the column already present — both deliberate no-ops.

Revision ID: 0001a2b3c4d5
Revises:
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001a2b3c4d5"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from gpu_service.domain.base import gpu_metadata

    gpu_metadata.create_all(op.get_bind())


def downgrade() -> None:
    from gpu_service.domain.base import gpu_metadata

    gpu_metadata.drop_all(op.get_bind())
