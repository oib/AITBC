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
down_revision: str | None = "d4e8b91c0a37"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    sa.String()
    for table_name, columns in [
        (
            "agent_stake",
            [
                sa.Column("id", sa.Integer(), nullable=False),
                sa.Column("chain_id", sa.String(), nullable=False),
                sa.Column("stake_id", sa.String(), nullable=False),
                sa.Column("staker_address", sa.String(), nullable=False),
                sa.Column("agent_wallet", sa.String(), nullable=False),
                sa.Column("amount", sa.BigInteger(), nullable=False),
                sa.Column("lock_period", sa.Integer(), nullable=False, server_default="30"),
                sa.Column("locked_until", sa.DateTime(), nullable=False),
                sa.Column("status", sa.String(), nullable=False, server_default="active"),
                sa.Column("unbonding_at", sa.DateTime(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
                sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            ],
        ),
        (
            "agent_stake_memo",
            [
                sa.Column("id", sa.Integer(), nullable=False),
                sa.Column("chain_id", sa.String(), nullable=False),
                sa.Column("kind", sa.String(), nullable=False),
                sa.Column("external_id", sa.String(), nullable=False, server_default=""),
                sa.Column("payload", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            ],
        ),
        (
            "bounty_contract",
            [
                sa.Column("id", sa.Integer(), nullable=False),
                sa.Column("chain_id", sa.String(), nullable=False),
                sa.Column("bounty_id", sa.String(), nullable=False),
                sa.Column("creator_address", sa.String(), nullable=False),
                sa.Column("reward_amount", sa.BigInteger(), nullable=False),
                sa.Column("remaining_amount", sa.BigInteger(), nullable=False),
                sa.Column("status", sa.String(), nullable=False, server_default="active"),
                sa.Column("winner_address", sa.String(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
                sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            ],
        ),
        (
            "bounty_submission",
            [
                sa.Column("id", sa.Integer(), nullable=False),
                sa.Column("chain_id", sa.String(), nullable=False),
                sa.Column("bounty_id", sa.String(), nullable=False),
                sa.Column("submission_id", sa.String(), nullable=False),
                sa.Column("submitter_address", sa.String(), nullable=False),
                sa.Column("status", sa.String(), nullable=False, server_default="pending"),
                sa.Column("payload", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
                sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            ],
        ),
    ]:
        op.create_table(
            table_name,
            *columns,
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(f"ix_{table_name}_chain_id", table_name, ["chain_id"])
        op.create_index(f"ix_{table_name}_status", table_name, ["status"])
        if table_name == "agent_stake":
            op.create_index("ix_agent_stake_stake_id", "agent_stake", ["stake_id"], unique=False)
            op.create_index("ix_agent_stake_staker_address", "agent_stake", ["staker_address"], unique=False)
            op.create_index("ix_agent_stake_agent_wallet", "agent_stake", ["agent_wallet"], unique=False)
            op.create_unique_constraint("uix_agent_stake_chain_id", "agent_stake", ["chain_id", "stake_id"])
        if table_name == "bounty_contract":
            op.create_index("ix_bounty_contract_bounty_id", "bounty_contract", ["bounty_id"], unique=False)
            op.create_index("ix_bounty_contract_creator_address", "bounty_contract", ["creator_address"], unique=False)
            op.create_unique_constraint("uix_bounty_contract_chain_id", "bounty_contract", ["chain_id", "bounty_id"])
        if table_name == "bounty_submission":
            op.create_index("ix_bounty_submission_bounty_id", "bounty_submission", ["bounty_id"], unique=False)
            op.create_index("ix_bounty_submission_submission_id", "bounty_submission", ["submission_id"], unique=False)
            op.create_unique_constraint("uix_bounty_submission_chain_id", "bounty_submission", ["chain_id", "submission_id"])


def downgrade() -> None:
    for table in ("bounty_submission", "bounty_contract", "agent_stake_memo", "agent_stake"):
        op.drop_table(table)
