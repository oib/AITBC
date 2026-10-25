"""Heal marketplace_regions.status rows seeded with lowercase labels.

``add_global_marketplace`` seeded the four default regions with ``'active'``.
On PostgreSQL that row never lands: 001 created ``status`` as the
``regionstatus`` enum whose labels are the member *names* ``'ACTIVE'`` …
``'DEPRECATED'``, so the INSERT aborts the upgrade. SQLite accepts any
string, so databases that already applied the revision carry lowercase
rows that the model's enum lookups (which bind ``'ACTIVE'``) never match.

The seed itself is corrected in ``add_global_marketplace`` for fresh
upgrades; this revision heals databases that already took the lowercase
values. ``CAST(status AS VARCHAR)`` keeps the predicate portable -- a bare
``status = 'active'`` is an invalid-enum-literal error on PostgreSQL
before a single row is read.

Revision ID: f7e8d9c0b1a2
Revises: c3a91f7e5b02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7e8d9c0b1a2"
down_revision: str | Sequence[str] | None = "c3a91f7e5b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REGIONSTATUS = ("ACTIVE", "INACTIVE", "MAINTENANCE", "DEPRECATED")


def upgrade() -> None:
    bind = op.get_bind()
    for label in _REGIONSTATUS:
        bind.execute(
            sa.text("UPDATE marketplace_regions SET status = :label WHERE CAST(status AS VARCHAR) = :lower"),
            {"label": label, "lower": label.lower()},
        )


def downgrade() -> None:
    # Writing invalid enum labels back is the defect this revision removes;
    # there is nothing safe to restore, so the step back is a no-op.
    pass
