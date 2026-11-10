"""add expires_at to inter_chain_trades

Revision ID: 005_v1562_trade_expiry
Revises: 004
Create Date: 2026-11-10 12:30:00.000000+00:00

#1562: pending inter-chain trades had no expiry — a trade that never
matched stayed 'pending' forever. New rows get a TTL at create time;
legacy rows keep NULL (never expire).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "005_v1562_trade_expiry"
down_revision = "004_v024_exchange_payment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inter_chain_trades", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("inter_chain_trades", "expires_at")
