"""add expires_at to trade_settlements

Revision ID: 006_v1554_settlement_expiry
Revises: 005_v1562_trade_expiry
Create Date: 2026-11-11 00:00:00.000000+00:00

#1554: TradeSettlement had no expires_at — a settlement stuck in SETTLING
parked forever. New rows get a TTL at create time (TRADE_SETTLEMENT_TTL_SECONDS,
default 7d); legacy rows keep NULL and are not expired.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "006_v1554_settlement_expiry"
down_revision = "005_v1562_trade_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trade_settlements", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_settlements", "expires_at")
