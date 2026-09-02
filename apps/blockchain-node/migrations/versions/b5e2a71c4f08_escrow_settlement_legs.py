"""Record the paid and returned legs of an escrow settlement.

A metered release bills what the job actually used and returns the rest to the
buyer, so `amount` alone no longer says how much the provider was paid. Add the
two columns and back-fill settled rows, all of which moved the whole lock.

Revision ID: b5e2a71c4f08
Revises: 498540b266b4
Create Date: 2026-09-02 00:00:00.000000
"""

from __future__ import annotations


import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e2a71c4f08"
down_revision: str | None = "498540b266b4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for col in ("released_amount", "refunded_amount"):
        try:
            op.add_column("escrow", sa.Column(col, sa.Integer(), nullable=True))
        except Exception:
            pass
    # Every settlement made before this migration moved the whole locked amount.
    bind.execute(
        sa.text("UPDATE escrow SET released_amount = amount WHERE released_at IS NOT NULL AND released_amount IS NULL")
    )
    bind.execute(
        sa.text("UPDATE escrow SET refunded_amount = amount WHERE refunded_at IS NOT NULL AND refunded_amount IS NULL")
    )


def downgrade() -> None:
    for col in ("refunded_amount", "released_amount"):
        try:
            op.drop_column("escrow", col)
        except Exception:
            pass
