"""Add reward_payouts table with a duplicate-payout constraint.

The RewardPayout model has existed since v0.6.7 with the docstring "prevent duplicate
payouts", but no migration ever created its table and no code ever wrote to it.
Duplicate protection lived entirely in RewardPolicy's in-process dicts, so a restart or a
second replica lost it and the same miner could be paid twice for the same epoch.

The unique constraint below is the guarantee. It is enforced by the database, so it holds
across restarts, across replicas, and across concurrent distribution runs.

Revision ID: e5d4f8a9b0c1
Revises: d4c3e7f8a9b0
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e5d4f8a9b0c1"
down_revision = "d4c3e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reward_payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("miner_id", sa.String(64), nullable=False),
        sa.Column("chain_id", sa.String(64), nullable=False),
        sa.Column("epoch_number", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        # One payout row per miner per chain per epoch. This is what makes distribution
        # idempotent: a second attempt hits the constraint instead of paying again.
        sa.UniqueConstraint("miner_id", "chain_id", "epoch_number", name="uq_reward_payout_miner_chain_epoch"),
    )
    op.create_index("ix_reward_payouts_miner_id", "reward_payouts", ["miner_id"], if_not_exists=True)
    op.create_index("ix_reward_payouts_chain_id", "reward_payouts", ["chain_id"], if_not_exists=True)
    op.create_index("ix_reward_payouts_epoch_number", "reward_payouts", ["epoch_number"], if_not_exists=True)
    # Reconciliation queries look for rows stuck in pending after a crash between claim
    # and submission.
    op.create_index("ix_reward_payouts_status", "reward_payouts", ["status"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_reward_payouts_status", table_name="reward_payouts", if_exists=True)
    op.drop_index("ix_reward_payouts_epoch_number", table_name="reward_payouts", if_exists=True)
    op.drop_index("ix_reward_payouts_chain_id", table_name="reward_payouts", if_exists=True)
    op.drop_index("ix_reward_payouts_miner_id", table_name="reward_payouts", if_exists=True)
    op.drop_table("reward_payouts")
