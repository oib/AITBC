"""Add energy floor quote and GPU resource columns.

Revision ID: f53990f9d6cc
Revises: 1c58c844d95e
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op, context
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f53990f9d6cc"
down_revision: str | None = "1c58c844d95e"
branch_labels: str | None = None
depends_on: str | None = None


def _column_exists(table: str, column: str) -> bool:
    """Check whether a column already exists on a table.

    Guards against duplicate-column failures on fresh databases where
    ``001_initial_migration`` has already created the current schema via
    ``SQLModel.metadata.create_all``.
    """
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _add_column_if_absent(table: str, column: str, col_type: sa.types.TypeEngine) -> None:
    if not _column_exists(table, column):
        op.add_column(table, sa.Column(column, col_type, nullable=True))


def upgrade() -> None:
    """Add nullable protected-rental columns to job, gpu_registry and gpu_bookings."""
    # job table
    _add_column_if_absent("job", "protected", sa.Boolean())
    _add_column_if_absent("job", "resource_id", sa.String(length=255))
    _add_column_if_absent("job", "model_id", sa.String(length=255))
    _add_column_if_absent("job", "gpu_count", sa.Integer())
    _add_column_if_absent("job", "duration_seconds", sa.Integer())
    _add_column_if_absent("job", "energy_quote_snapshot", sa.JSON())

    # gpu_registry table
    _add_column_if_absent("gpu_registry", "model_id", sa.String(length=255))
    _add_column_if_absent("gpu_registry", "resource_id", sa.String(length=255))
    _add_column_if_absent("gpu_registry", "protected", sa.Boolean())

    # gpu_bookings table
    _add_column_if_absent("gpu_bookings", "protected", sa.Boolean())
    _add_column_if_absent("gpu_bookings", "resource_id", sa.String(length=255))
    _add_column_if_absent("gpu_bookings", "model_id", sa.String(length=255))
    _add_column_if_absent("gpu_bookings", "gpu_count", sa.Integer())
    _add_column_if_absent("gpu_bookings", "duration_seconds", sa.Integer())
    _add_column_if_absent("gpu_bookings", "energy_quote_snapshot", sa.JSON())

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
