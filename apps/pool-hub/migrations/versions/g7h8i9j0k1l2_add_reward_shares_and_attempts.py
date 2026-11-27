"""Add reward_shares table and reward_payouts.reconcile_attempts (#3058).

AUDIT-POOLHUB-REWARD-PIPELINE-1: the reward pipeline is dead scaffold, and two
of its latent defects are fixed here at the schema level:

- ``reward_shares`` persists per-epoch miner shares with an ``evidence_tx_hash``
  and ``verified`` flag. The in-memory RewardPolicy share ledger is replaced on
  the payout path by this table, so shares survive restarts and can only be
  written through the evidence-requiring verified-share API.
- ``reward_payouts.reconcile_attempts`` bounds the reconciliation sweep's
  resubmission of proven-absent payout rows.
- ``reward_payouts.recipient`` records the wallet each payout attempt paid
  (respin: wallet-rotation-safe reconciliation matching).

Revision ID: g7h8i9j0k1l2
Revises: a7f2c9d1e4b6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "g7h8i9j0k1l2"
down_revision = "a7f2c9d1e4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reward_payouts",
        sa.Column("reconcile_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    # #3058 respin: recipient persisted at submit time so reconciliation
    # matches the address the payout actually paid (wallet rotation safe).
    op.add_column(
        "reward_payouts",
        sa.Column("recipient", sa.String(128), nullable=True),
    )
    op.create_table(
        "reward_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("miner_id", sa.String(64), nullable=False),
        sa.Column("chain_id", sa.String(64), nullable=False),
        sa.Column("epoch_number", sa.Integer(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(64), nullable=False, server_default="verified_chain"),
        sa.Column("evidence_tx_hash", sa.String(128), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("miner_id", "chain_id", "epoch_number", "source", name="uq_reward_share_miner_chain_epoch_source"),
    )
    op.create_index("ix_reward_shares_miner_id", "reward_shares", ["miner_id"], if_not_exists=True)
    op.create_index("ix_reward_shares_chain_id", "reward_shares", ["chain_id"], if_not_exists=True)
    op.create_index("ix_reward_shares_epoch_number", "reward_shares", ["epoch_number"], if_not_exists=True)


def downgrade() -> None:
    op.drop_column("reward_payouts", "recipient")
    op.drop_index("ix_reward_shares_epoch_number", table_name="reward_shares", if_exists=True)
    op.drop_index("ix_reward_shares_chain_id", table_name="reward_shares", if_exists=True)
    op.drop_index("ix_reward_shares_miner_id", table_name="reward_shares", if_exists=True)
    op.drop_table("reward_shares")
    op.drop_column("reward_payouts", "reconcile_attempts")
