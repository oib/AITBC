"""Add energy floor quote and GPU resource columns.

Revision ID: f53990f9d6cc
Revises: 1c58c844d95e
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f53990f9d6cc"
down_revision: str | None = "1c58c844d95e"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add nullable protected-rental columns to job, gpu_registry and gpu_bookings."""
    # job table
    op.add_column("job", sa.Column("protected", sa.Boolean(), nullable=True))
    op.add_column("job", sa.Column("resource_id", sa.String(length=255), nullable=True))
    op.add_column("job", sa.Column("model_id", sa.String(length=255), nullable=True))
    op.add_column("job", sa.Column("gpu_count", sa.Integer(), nullable=True))
    op.add_column("job", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column("job", sa.Column("energy_quote_snapshot", sa.JSON(), nullable=True))

    # gpu_registry table
    op.add_column("gpu_registry", sa.Column("model_id", sa.String(length=255), nullable=True))
    op.add_column("gpu_registry", sa.Column("resource_id", sa.String(length=255), nullable=True))
    op.add_column("gpu_registry", sa.Column("protected", sa.Boolean(), nullable=True))

    # gpu_bookings table
    op.add_column("gpu_bookings", sa.Column("protected", sa.Boolean(), nullable=True))
    op.add_column("gpu_bookings", sa.Column("resource_id", sa.String(length=255), nullable=True))
    op.add_column("gpu_bookings", sa.Column("model_id", sa.String(length=255), nullable=True))
    op.add_column("gpu_bookings", sa.Column("gpu_count", sa.Integer(), nullable=True))
    op.add_column("gpu_bookings", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column("gpu_bookings", sa.Column("energy_quote_snapshot", sa.JSON(), nullable=True))

    # Backfill boolean flags to false so existing rows remain unprotected.
    op.execute("UPDATE job SET protected = 0 WHERE protected IS NULL")
    op.execute("UPDATE gpu_registry SET protected = 0 WHERE protected IS NULL")
    op.execute("UPDATE gpu_bookings SET protected = 0 WHERE protected IS NULL")


def downgrade() -> None:
    """Remove energy floor columns."""
    op.drop_column("gpu_bookings", "energy_quote_snapshot")
    op.drop_column("gpu_bookings", "duration_seconds")
    op.drop_column("gpu_bookings", "gpu_count")
    op.drop_column("gpu_bookings", "model_id")
    op.drop_column("gpu_bookings", "resource_id")
    op.drop_column("gpu_bookings", "protected")

    op.drop_column("gpu_registry", "protected")
    op.drop_column("gpu_registry", "resource_id")
    op.drop_column("gpu_registry", "model_id")

    op.drop_column("job", "energy_quote_snapshot")
    op.drop_column("job", "duration_seconds")
    op.drop_column("job", "gpu_count")
    op.drop_column("job", "model_id")
    op.drop_column("job", "resource_id")
    op.drop_column("job", "protected")
