"""add agent spend sessions and wallet audit log

Revision ID: e4a1b2c3d4e5
Revises: d3e4f5a6b7c8
Create Date: 2026-11-04 22:15:00.000000+00:00

AGENT-SPEND-A-1 Phase A: session credentials and audit trail.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_spend_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("owner_address", sa.String(length=42), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("cap_ait", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("used_ait", sa.Numeric(precision=20, scale=8), nullable=False, server_default="0"),
        sa.Column("allowed_ops", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_spend_sessions_agent_id",
        "agent_spend_sessions",
        ["agent_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_agent_spend_sessions_agent_chain",
        "agent_spend_sessions",
        ["agent_id", "chain_id"],
        unique=False,
        if_not_exists=True,
    )

    op.create_table(
        "wallet_audit_log",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=32), nullable=True),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("amount_ait", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("op", sa.String(length=64), nullable=True),
        sa.Column("ref", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_wallet_audit_log_agent_id",
        "wallet_audit_log",
        ["agent_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_audit_log_agent_id", table_name="wallet_audit_log", if_exists=True)
    op.drop_table("wallet_audit_log", if_exists=True)
    op.drop_index("ix_agent_spend_sessions_agent_chain", table_name="agent_spend_sessions", if_exists=True)
    op.drop_index("ix_agent_spend_sessions_agent_id", table_name="agent_spend_sessions", if_exists=True)
    op.drop_table("agent_spend_sessions", if_exists=True)
