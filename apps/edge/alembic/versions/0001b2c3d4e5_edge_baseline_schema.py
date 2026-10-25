"""Baseline: create every SQLModel.metadata table on an empty database.

The single existing revision (``e1c47b09f2a6``) is alteration-only — it
converts four money columns — so ``alembic upgrade head`` on a fresh
database produced only ``alembic_version`` and left ``init_db`` /
``create_all`` to build the real schema untracked. This baseline makes
the migration graph self-sufficient: every table registered on
``SQLModel.metadata`` by ``aitbc_edge.schemas`` is created here,
``checkfirst`` so already-deployed databases pass through untouched.

The money-column revision that follows then finds the columns already
``Numeric(20, 8)`` on a fresh database — a deliberate no-op.

Revision ID: 0001b2c3d4e5
Revises:
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001b2c3d4e5"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Importing the schema modules registers the tables, mirroring env.py.
    from aitbc_edge.schemas import database, gpu, island, metrics, serve  # noqa: F401
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    from aitbc_edge.schemas import database, gpu, island, metrics, serve  # noqa: F401
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(op.get_bind())
