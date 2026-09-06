"""Add energy floor quote snapshot columns to escrow.

Revision ID: ec9a04333809
Revises: 9f8e7d6c5b4a
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op, context

# revision identifiers, used by Alembic.
revision: str = "ec9a04333809"
down_revision: str | None = "9f8e7d6c5b4a"
branch_labels: str | None = None
depends_on: str | None = None


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    """Check whether a column already exists on a table.

    Guards against duplicate-column failures on fresh databases where
    ``SQLModel.metadata.create_all`` has already created the current schema.
    """
    if context.is_offline_mode():
        return False
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table_name))


def upgrade() -> None:
    """Add nullable protected-rental columns to the escrow table."""
    bind = op.get_bind()
    columns = [
        ("protected", sa.Boolean()),
        ("energy_quote_snapshot", sa.JSON()),
        ("energy_quote_id", sa.String(length=64)),
        ("energy_net_floor_units", sa.BigInteger()),
        ("energy_provider_credit_units", sa.BigInteger()),
        ("energy_fee_basis_points", sa.Integer()),
    ]
    for col_name, col_type in columns:
        if not _column_exists(bind, "escrow", col_name):
            op.add_column("escrow", sa.Column(col_name, col_type, nullable=True))

    # Backfill existing rows as unprotected.
    op.execute("UPDATE escrow SET protected = 0 WHERE protected IS NULL")


def downgrade() -> None:
    """Remove energy floor columns."""
    op.drop_column("escrow", "energy_fee_basis_points")
    op.drop_column("escrow", "energy_provider_credit_units")
    op.drop_column("escrow", "energy_net_floor_units")
    op.drop_column("escrow", "energy_quote_id")
    op.drop_column("escrow", "energy_quote_snapshot")
    op.drop_column("escrow", "protected")
