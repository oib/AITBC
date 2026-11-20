"""Add job.started_at — the RUNNING-entry timestamp (#2317).

A protected ``gpu_compute`` rental's ``expires_at`` is a queue deadline; the
claim CAS (#2306) extends it once, but a miner restart re-dispatches the same
RUNNING job and the restarted miner re-holds the *full* purchased duration, so
``expires_at`` can still pass mid-second-rental and the stale-job reaper
refunds the buyer while the provider works unpaid.

``started_at`` is stamped by the QUEUED→RUNNING claim CAS and anchors the
rental deadline (``started_at + duration + slack``) independently of
``expires_at``. Nullable: jobs already RUNNING at deploy time keep NULL and
fall back to the previous ``expires_at`` behaviour — no backfill, because the
claim time of a legacy row cannot be recovered reliably.

Revision ID: a2317b2c3d4e
Revises: b3c4d5e6f7a8
Create Date: 2026-11-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a2317b2c3d4e"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        existing_cols: set[str] = set()
    else:
        bind = op.get_bind()
        existing_cols = {str(c["name"]) for c in inspect(bind).get_columns("job") if c.get("name")}
    if "started_at" not in existing_cols:
        op.add_column("job", sa.Column("started_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "started_at")
