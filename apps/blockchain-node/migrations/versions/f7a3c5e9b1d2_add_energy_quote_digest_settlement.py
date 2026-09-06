"""Add energy quote digest and settlement binding columns to escrow.

Revision ID: f7a3c5e9b1d2
Revises: ec9a04333809
Create Date: 2026-09-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a3c5e9b1d2"
down_revision: str | None = "ec9a04333809"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add nullable quote-digest and settlement-binding columns to escrow."""
    op.add_column("escrow", sa.Column("energy_quote_digest", sa.String(length=128), nullable=True))
    op.add_column("escrow", sa.Column("energy_settlement_route", sa.String(length=32), nullable=True))
    op.add_column("escrow", sa.Column("energy_settlement_asset", sa.String(length=64), nullable=True))
    op.add_column("escrow", sa.Column("energy_settlement_unit_scale", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Remove quote-digest and settlement-binding columns."""
    op.drop_column("escrow", "energy_settlement_unit_scale")
    op.drop_column("escrow", "energy_settlement_asset")
    op.drop_column("escrow", "energy_settlement_route")
    op.drop_column("escrow", "energy_quote_digest")
