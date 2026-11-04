"""Add optional agent_id binding columns on escrow rows.

Revision ID: a8b9c0d1e2f3
Revises: d4e8b2f61a39
Create Date: 2026-11-04 22:30:00.000000+00:00

AGENT-SPEND-D-1: persist buyer_agent_id / provider_agent_id at lock for credential rotation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "d4e8b2f61a39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "escrow" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("escrow")}
    if "buyer_agent_id" not in existing:
        op.add_column("escrow", sa.Column("buyer_agent_id", sa.String(length=128), nullable=True))
    if "provider_agent_id" not in existing:
        op.add_column("escrow", sa.Column("provider_agent_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "escrow" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("escrow")}
    if "provider_agent_id" in existing:
        op.drop_column("escrow", "provider_agent_id")
    if "buyer_agent_id" in existing:
        op.drop_column("escrow", "buyer_agent_id")
