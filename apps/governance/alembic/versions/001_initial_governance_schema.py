"""Initial governance schema with v0.4.12 enhancements

Revision ID: 001
Revises: 
Create Date: 2026-06-07 18:58:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create governance_profiles table
    op.create_table(
        "governance_profiles",
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("voting_power", sa.Float(), nullable=False),
        sa.Column("delegated_power", sa.Float(), nullable=False),
        sa.Column("total_votes_cast", sa.Integer(), nullable=False),
        sa.Column("proposals_created", sa.Integer(), nullable=False),
        sa.Column("proposals_passed", sa.Integer(), nullable=False),
        sa.Column("delegate_to", sa.String(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_voted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_governance_profiles_user_id"), "governance_profiles", ["user_id"], unique=False)

    # Create proposals table with v0.4.12 fields
    op.create_table(
        "proposals",
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("proposer_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("proposal_type", sa.String(), nullable=False),
        sa.Column("proposal_value", postgresql.JSON(), nullable=True),
        sa.Column("quorum_required", sa.Float(), nullable=False),
        sa.Column("yes_votes", sa.Float(), nullable=False),
        sa.Column("no_votes", sa.Float(), nullable=False),
        sa.Column("execution_tx_hash", sa.String(), nullable=True),
        sa.Column("execution_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposal_metadata", postgresql.JSON(), nullable=True),
        sa.Column("execution_payload", postgresql.JSON(), nullable=True),
        sa.Column("votes_for", sa.Float(), nullable=False),
        sa.Column("votes_against", sa.Float(), nullable=False),
        sa.Column("votes_abstain", sa.Float(), nullable=False),
        sa.Column("passing_threshold", sa.Float(), nullable=False),
        sa.Column("snapshot_block", sa.Integer(), nullable=True),
        sa.Column("snapshot_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voting_starts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voting_ends", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["proposer_id"], ["governance_profiles.profile_id"]),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index(op.f("idx_proposals_status"), "proposals", ["status"], unique=False)
    op.create_index(op.f("idx_proposals_voting_period"), "proposals", ["voting_starts", "voting_ends"], unique=False)
    op.create_index(op.f("idx_proposals_proposer"), "proposals", ["proposer_id"], unique=False)

    # Create votes table with v0.4.12 fields
    op.create_table(
        "votes",
        sa.Column("vote_id", sa.String(), nullable=False),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("voter_id", sa.String(), nullable=False),
        sa.Column("vote_type", sa.String(), nullable=False),
        sa.Column("voting_power_used", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("power_at_snapshot", sa.Float(), nullable=False),
        sa.Column("delegated_power_at_snapshot", sa.Float(), nullable=False),
        sa.Column("voting_power", sa.Float(), nullable=False),
        sa.Column("vote_weight", sa.Float(), nullable=False),
        sa.Column("delegated_from", sa.String(), nullable=True),
        sa.Column("signature", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.proposal_id"]),
        sa.ForeignKeyConstraint(["voter_id"], ["governance_profiles.profile_id"]),
        sa.PrimaryKeyConstraint("vote_id"),
    )
    op.create_index(op.f("idx_votes_proposal"), "votes", ["proposal_id"], unique=False)
    op.create_index(op.f("idx_votes_voter"), "votes", ["voter_id"], unique=False)
    op.create_index(op.f("idx_votes_delegated"), "votes", ["delegated_from"], unique=False)

    # Create delegations table
    op.create_table(
        "delegations",
        sa.Column("delegation_id", sa.String(), nullable=False),
        sa.Column("delegator_address", sa.String(), nullable=False),
        sa.Column("delegate_address", sa.String(), nullable=False),
        sa.Column("voting_power", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("delegation_id"),
    )
    op.create_index(op.f("idx_delegations_delegator"), "delegations", ["delegator_address"], unique=False)
    op.create_index(op.f("idx_delegations_delegate"), "delegations", ["delegate_address"], unique=False)
    op.create_index(op.f("idx_delegations_active"), "delegations", ["is_active"], unique=False)

    # Create governance_tokens table
    op.create_table(
        "governance_tokens",
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("holder_address", sa.String(), nullable=False),
        sa.Column("token_balance", sa.Float(), nullable=False),
        sa.Column("staked_tokens", sa.Float(), nullable=False),
        sa.Column("voting_power", sa.Float(), nullable=False),
        sa.Column("rewards_claimed", sa.Float(), nullable=False),
        sa.Column("rewards_pending", sa.Float(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("holder_address"),
    )
    op.create_index(op.f("idx_tokens_holder"), "governance_tokens", ["holder_address"], unique=False)
    op.create_index(op.f("idx_tokens_voting_power"), "governance_tokens", ["voting_power"], unique=False)

    # Create token_stakes table
    op.create_table(
        "token_stakes",
        sa.Column("stake_id", sa.String(), nullable=False),
        sa.Column("staker_address", sa.String(), nullable=False),
        sa.Column("amount_staked", sa.Float(), nullable=False),
        sa.Column("lock_period_days", sa.Integer(), nullable=False),
        sa.Column("staked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unstakes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("rewards_earned", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("stake_id"),
    )
    op.create_index(op.f("idx_stakes_staker"), "token_stakes", ["staker_address"], unique=False)
    op.create_index(op.f("idx_stakes_active"), "token_stakes", ["is_active"], unique=False)
    op.create_index(op.f("idx_stakes_unstake"), "token_stakes", ["unstakes_at"], unique=False)

    # Create proposal_execution_log table
    op.create_table(
        "proposal_execution_log",
        sa.Column("log_id", sa.String(), nullable=False),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("execution_step", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", postgresql.JSON(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.proposal_id"]),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_index(op.f("idx_exec_log_proposal"), "proposal_execution_log", ["proposal_id"], unique=False)
    op.create_index(op.f("idx_exec_log_status"), "proposal_execution_log", ["status"], unique=False)
    op.create_index(op.f("idx_exec_log_timestamp"), "proposal_execution_log", ["executed_at"], unique=False)

    # Create dao_treasury table
    op.create_table(
        "dao_treasury",
        sa.Column("treasury_id", sa.String(), nullable=False),
        sa.Column("total_balance", sa.Float(), nullable=False),
        sa.Column("allocated_funds", sa.Float(), nullable=False),
        sa.Column("asset_breakdown", postgresql.JSON(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("treasury_id"),
    )

    # Create transparency_reports table
    op.create_table(
        "transparency_reports",
        sa.Column("report_id", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("total_proposals", sa.Integer(), nullable=False),
        sa.Column("passed_proposals", sa.Integer(), nullable=False),
        sa.Column("active_voters", sa.Integer(), nullable=False),
        sa.Column("total_voting_power_participated", sa.Float(), nullable=False),
        sa.Column("treasury_inflow", sa.Float(), nullable=False),
        sa.Column("treasury_outflow", sa.Float(), nullable=False),
        sa.Column("metrics", postgresql.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )


def downgrade() -> None:
    # Drop tables in reverse order of creation
    op.drop_table("transparency_reports")
    op.drop_table("dao_treasury")
    op.drop_index(op.f("idx_exec_log_timestamp"), table_name="proposal_execution_log")
    op.drop_index(op.f("idx_exec_log_status"), table_name="proposal_execution_log")
    op.drop_index(op.f("idx_exec_log_proposal"), table_name="proposal_execution_log")
    op.drop_table("proposal_execution_log")
    op.drop_index(op.f("idx_stakes_unstake"), table_name="token_stakes")
    op.drop_index(op.f("idx_stakes_active"), table_name="token_stakes")
    op.drop_index(op.f("idx_stakes_staker"), table_name="token_stakes")
    op.drop_table("token_stakes")
    op.drop_index(op.f("idx_tokens_voting_power"), table_name="governance_tokens")
    op.drop_index(op.f("idx_tokens_holder"), table_name="governance_tokens")
    op.drop_table("governance_tokens")
    op.drop_index(op.f("idx_delegations_active"), table_name="delegations")
    op.drop_index(op.f("idx_delegations_delegate"), table_name="delegations")
    op.drop_index(op.f("idx_delegations_delegator"), table_name="delegations")
    op.drop_table("delegations")
    op.drop_index(op.f("idx_votes_delegated"), table_name="votes")
    op.drop_index(op.f("idx_votes_voter"), table_name="votes")
    op.drop_index(op.f("idx_votes_proposal"), table_name="votes")
    op.drop_table("votes")
    op.drop_index(op.f("idx_proposals_proposer"), table_name="proposals")
    op.drop_index(op.f("idx_proposals_voting_period"), table_name="proposals")
    op.drop_index(op.f("idx_proposals_status"), table_name="proposals")
    op.drop_table("proposals")
    op.drop_index(op.f("ix_governance_profiles_user_id"), table_name="governance_profiles")
    op.drop_table("governance_profiles")
