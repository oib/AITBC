"""Add escrow status, lock_tx_hash, refund_tx_hash and refunded_at columns.

Existing rows are back-filled:
- status = 'released' where released_at is not null
- status = 'refunded' where refunded_at is not null
- status = 'locked' otherwise

Revision ID: 498540b266b4
Revises: 46c9bffdf9c6
Create Date: 2026-08-24 00:00:00.000000
"""

from __future__ import annotations


import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "498540b266b4"
down_revision: str | None = "46c9bffdf9c6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for col, type_ in [
        ("status", sa.String()),
        ("lock_tx_hash", sa.String()),
        ("refunded_at", sa.DateTime()),
        ("refund_tx_hash", sa.String()),
    ]:
        try:
            op.add_column("escrow", sa.Column(col, type_, nullable=True))
        except Exception:
            pass
    # Back-fill status based on timestamps.
    bind.execute(
        sa.text(
            """
            UPDATE escrow
            SET status = CASE
                WHEN refunded_at IS NOT NULL THEN 'refunded'
                WHEN released_at IS NOT NULL THEN 'released'
                ELSE 'locked'
            END
            WHERE status IS NULL
            """
        )
    )
    # Default future rows to 'locked'.
    bind.execute(sa.text("UPDATE escrow SET status = 'locked' WHERE status IS NULL"))


def downgrade() -> None:
    for col in ("refund_tx_hash", "refunded_at", "lock_tx_hash", "status"):
        try:
            op.drop_column("escrow", col)
        except Exception:
            pass
