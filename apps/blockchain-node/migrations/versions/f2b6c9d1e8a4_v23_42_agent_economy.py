"""Add agent-economy tables for V23-42.

Revision ID: f2b6c9d1e8a4
Revises: d4e8b91c0a37
Create Date: 2026-08-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b6c9d1e8a4"
down_revision: str | None = "c9a4f1e2b73d"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "agent_stake",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.String(), nullable=False, index=True),
        sa.Column("stake_id", sa.String(), nullable=False, index=True),
        sa.Column("staker_address", sa.String(), nullable=False, index=True),
        sa.Column("agent_wallet", sa.String(), nullable=False, index=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("lock_period", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("locked_until", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active", index=True),
        sa.Column("unbonding_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_id", "stake_id", name="uix_agent_stake_chain_id"),
    )
    op.create_table(
        "agent_stake_memo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.String(), nullable=False, index=True),
        sa.Column("kind", sa.String(), nullable=False, index=True),
        sa.Column("external_id", sa.String(), nullable=False, server_default="", index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bounty_contract",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.String(), nullable=False, index=True),
        sa.Column("bounty_id", sa.String(), nullable=False, index=True),
        sa.Column("creator_address", sa.String(), nullable=False, index=True),
        sa.Column("reward_amount", sa.BigInteger(), nullable=False),
        sa.Column("remaining_amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active", index=True),
        sa.Column("winner_address", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_id", "bounty_id", name="uix_bounty_contract_chain_id"),
    )
    op.create_table(
        "bounty_submission",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.String(), nullable=False, index=True),
        sa.Column("bounty_id", sa.String(), nullable=False, index=True),
        sa.Column("submission_id", sa.String(), nullable=False, index=True),
        sa.Column("submitter_address", sa.String(), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending", index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_id", "submission_id", name="uix_bounty_submission_chain_id"),
    )


def downgrade() -> None:
    for table in ("bounty_submission", "bounty_contract", "agent_stake_memo", "agent_stake"):
        op.drop_table(table)
