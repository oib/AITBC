"""escrow relay agent binding columns

Revision ID: f5a6b7c8d9e0
Revises: e4a1b2c3d4e5
Create Date: 2026-11-04 22:30:00.000000+00:00

AGENT-SPEND-D-1: bind buyer/provider agent_id at escrow relay lock.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | Sequence[str] | None = "e4a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "escrow_relay",
        sa.Column("buyer_agent_id", sa.String(length=128), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "escrow_relay",
        sa.Column("provider_agent_id", sa.String(length=128), nullable=True),
        if_not_exists=True,
    )
    op.create_index(
        "ix_escrow_relay_buyer_agent_id",
        "escrow_relay",
        ["buyer_agent_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_escrow_relay_provider_agent_id",
        "escrow_relay",
        ["provider_agent_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_escrow_relay_provider_agent_id", table_name="escrow_relay", if_exists=True)
    op.drop_index("ix_escrow_relay_buyer_agent_id", table_name="escrow_relay", if_exists=True)
    op.drop_column("escrow_relay", "provider_agent_id", if_exists=True)
    op.drop_column("escrow_relay", "buyer_agent_id", if_exists=True)
