"""Add energy quote digest and settlement binding columns to escrow.

Revision ID: f7a3c5e9b1d2
Revises: ec9a04333809
Create Date: 2026-09-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op, context

# revision identifiers, used by Alembic.
revision: str = "f7a3c5e9b1d2"
down_revision: str | None = "ec9a04333809"
branch_labels: str | None = None
depends_on: str | None = None


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    """Check whether a column already exists on a table."""
    if context.is_offline_mode():
        return False
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table_name))


def upgrade() -> None:
    """Add nullable quote-digest and settlement-binding columns to escrow."""
    bind = op.get_bind()
    columns = [
        ("energy_quote_digest", sa.String(length=128)),
        ("energy_settlement_route", sa.String(length=32)),
        ("energy_settlement_asset", sa.String(length=64)),
        ("energy_settlement_unit_scale", sa.BigInteger()),
    ]
    for col_name, col_type in columns:
        if not _column_exists(bind, "escrow", col_name):
            op.add_column("escrow", sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    """Remove quote-digest and settlement-binding columns."""
    op.drop_column("escrow", "energy_settlement_unit_scale")
    op.drop_column("escrow", "energy_settlement_asset")
    op.drop_column("escrow", "energy_settlement_route")
    op.drop_column("escrow", "energy_quote_digest")
