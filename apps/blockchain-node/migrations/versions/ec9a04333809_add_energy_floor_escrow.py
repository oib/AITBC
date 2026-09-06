"""Add energy floor quote snapshot columns to escrow.

Revision ID: ec9a04333809
Revises: 9f8e7d6c5b4a
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec9a04333809"
down_revision: str | None = "9f8e7d6c5b4a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add nullable protected-rental columns to the escrow table."""
    op.add_column("escrow", sa.Column("protected", sa.Boolean(), nullable=True))
    op.add_column("escrow", sa.Column("energy_quote_snapshot", sa.JSON(), nullable=True))
    op.add_column("escrow", sa.Column("energy_quote_id", sa.String(length=64), nullable=True))
    op.add_column("escrow", sa.Column("energy_net_floor_units", sa.BigInteger(), nullable=True))
    op.add_column("escrow", sa.Column("energy_provider_credit_units", sa.BigInteger(), nullable=True))
    op.add_column("escrow", sa.Column("energy_fee_basis_points", sa.Integer(), nullable=True))

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
