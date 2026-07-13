"""Add developer platform and enhanced governance tables

Revision ID: add_developer_platform
Revises: add_global_marketplace
Create Date: 2026-02-28 23:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_developer_platform"
down_revision = "add_global_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create developer_profile table
    op.create_table(
        "developer_profile",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("wallet_address", sa.String(), nullable=False),
        sa.Column("github_handle", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("reputation_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("total_earned_aitbc", sa.Float(), nullable=False, default=0.0),
        sa.Column("skills", sa.JSON(), nullable=False, default=list),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wallet_address"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_developer_profile_wallet_address", "developer_profile", ["wallet_address"], unique=False, if_not_exists=True
    )

    # Create developer_certification table
    op.create_table(
        "developer_certification",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("developer_id", sa.String(), nullable=False),
        sa.Column("certification_name", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("issued_by", sa.String(), nullable=False),
        sa.Column("ipfs_credential_cid", sa.String(), nullable=True),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False, default=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["developer_profile.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    # Create regional_hub table
    op.create_table(
        "regional_hub",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("region_code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("lead_wallet_address", sa.String(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False, default=0),
        sa.Column("budget_allocation", sa.Float(), nullable=False, default=0.0),
        sa.Column("spent_budget", sa.Float(), nullable=False, default=0.0),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_code"),
        if_not_exists=True,
    )
    op.create_index("ix_regional_hub_region_code", "regional_hub", ["region_code"], unique=True, if_not_exists=True)

    # Create bounty_task table
    op.create_table(
        "bounty_task",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("required_skills", sa.JSON(), nullable=False, default=list),
        sa.Column("difficulty_level", sa.String(), nullable=False),
        sa.Column("reward_amount", sa.Float(), nullable=False),
        sa.Column("creator_address", sa.String(), nullable=False),
        sa.Column("assigned_developer_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, default="open"),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_developer_id"],
            ["developer_profile.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_bounty_task_status", "bounty_task", ["status"], unique=False, if_not_exists=True)
    op.create_index("ix_bounty_task_creator", "bounty_task", ["creator_address"], unique=False, if_not_exists=True)

    # Create bounty_submission table
    op.create_table(
        "bounty_submission",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("bounty_id", sa.String(), nullable=False),
        sa.Column("developer_id", sa.String(), nullable=False),
        sa.Column("github_pr_url", sa.String(), nullable=True),
        sa.Column("submission_notes", sa.String(), nullable=False, default=""),
        sa.Column("is_approved", sa.Boolean(), nullable=False, default=False),
        sa.Column("review_notes", sa.String(), nullable=True),
        sa.Column("reviewer_address", sa.String(), nullable=True),
        sa.Column("tx_hash_reward", sa.String(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["bounty_id"],
            ["bounty_task.id"],
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["developer_profile.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_bounty_submission_bounty_id", "bounty_submission", ["bounty_id"], unique=False, if_not_exists=True)
    op.create_index(
        "ix_bounty_submission_developer_id", "bounty_submission", ["developer_id"], unique=False, if_not_exists=True
    )

    # Create regional_council table
    op.create_table(
        "regional_council",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("council_name", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("jurisdiction", sa.String(), nullable=False),
        sa.Column("council_members", sa.JSON(), nullable=False, default=list),
        sa.Column("budget_allocation", sa.Float(), nullable=False, default=0.0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_regional_council_region", "regional_council", ["region"], unique=False, if_not_exists=True)

    # Create regional_proposal table
    op.create_table(
        "regional_proposal",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("council_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("proposal_type", sa.String(), nullable=False),
        sa.Column("amount_requested", sa.Float(), nullable=False),
        sa.Column("proposer_address", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, default="active"),
        sa.Column("voting_deadline", sa.DateTime(), nullable=False),
        sa.Column("votes_for", sa.Float(), nullable=False, default=0.0),
        sa.Column("votes_against", sa.Float(), nullable=False, default=0.0),
        sa.Column("votes_abstain", sa.Float(), nullable=False, default=0.0),
        sa.Column("total_voting_power", sa.Float(), nullable=False, default=0.0),
        sa.Column("quorum_reached", sa.Boolean(), nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["council_id"],
            ["regional_council.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_regional_proposal_council_id", "regional_proposal", ["council_id"], unique=False, if_not_exists=True)
    op.create_index("ix_regional_proposal_status", "regional_proposal", ["status"], unique=False, if_not_exists=True)

    # Create staking_pool table
    op.create_table(
        "staking_pool",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("pool_name", sa.String(), nullable=False),
        sa.Column("developer_address", sa.String(), nullable=False),
        sa.Column("base_apy", sa.Float(), nullable=False),
        sa.Column("reputation_multiplier", sa.Float(), nullable=False),
        sa.Column("total_staked", sa.Float(), nullable=False, default=0.0),
        sa.Column("stakers_count", sa.Integer(), nullable=False, default=0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_staking_pool_developer_address", "staking_pool", ["developer_address"], unique=False, if_not_exists=True
    )

    # Create staking_position table
    op.create_table(
        "staking_position",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("pool_id", sa.String(), nullable=False),
        sa.Column("staker_address", sa.String(), nullable=False),
        sa.Column("amount_staked", sa.Float(), nullable=False),
        sa.Column("apy_at_stake", sa.Float(), nullable=False),
        sa.Column("rewards_earned", sa.Float(), nullable=False, default=0.0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pool_id"],
            ["staking_pool.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_staking_position_pool_id", "staking_position", ["pool_id"], unique=False, if_not_exists=True)
    op.create_index(
        "ix_staking_position_staker_address", "staking_position", ["staker_address"], unique=False, if_not_exists=True
    )

    # Create treasury_allocation table
    op.create_table(
        "treasury_allocation",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("council_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("recipient_address", sa.String(), nullable=False),
        sa.Column("approver_address", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, default="pending"),
        sa.Column("tx_hash", sa.String(), nullable=True),
        sa.Column("allocated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["council_id"],
            ["regional_council.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_treasury_allocation_proposal_id", "treasury_allocation", ["proposal_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_treasury_allocation_recipient_address",
        "treasury_allocation",
        ["recipient_address"],
        unique=False,
        if_not_exists=True,
    )

    # Insert default data
    # Create sample regional hubs
    op.execute("""
        INSERT INTO regional_hub (id, region_code, name, description, lead_wallet_address, member_count, budget_allocation, spent_budget, created_at)
        VALUES
            ('hub_us_east_001', 'us-east', 'US Eastern Developer Hub', 'Primary developer hub for US East region', '0x1234567890abcdef', 0, 0.0, 0.0, CURRENT_TIMESTAMP),
            ('hub_eu_west_001', 'eu-west', 'EU Western Developer Hub', 'Primary developer hub for EU West region', '0xabcdef1234567890', 0, 0.0, 0.0, CURRENT_TIMESTAMP),
            ('hub_apac_001', 'asia-pacific', 'Asia-Pacific Developer Hub', 'Primary developer hub for Asia-Pacific region', '0x7890abcdef123456', 0, 0.0, 0.0, CURRENT_TIMESTAMP)
    """)

    # Create sample regional councils
    op.execute("""
        INSERT INTO regional_council (id, council_name, region, jurisdiction, council_members, budget_allocation, is_active, created_at, updated_at)
        VALUES
            ('council_us_east_001', 'US Eastern Governance Council', 'us-east', 'United States',
             '["0x1234567890abcdef", "0x2345678901bcdef", "0x3456789012cdefa"]', 100000.0, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('council_eu_west_001', 'EU Western Governance Council', 'eu-west', 'European Union',
             '["0xabcdef1234567890", "0xbcdef12345678901", "0xcdef123456789012"]', 80000.0, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('council_apac_001', 'Asia-Pacific Governance Council', 'asia-pacific', 'Singapore',
             '["0x7890abcdef123456", "0x890abcdef123456", "0x90abcdef1234567"]', 60000.0, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)

    # Create sample staking pools
    op.execute("""
        INSERT INTO staking_pool (id, pool_name, developer_address, base_apy, reputation_multiplier, total_staked, stakers_count, is_active, created_at, updated_at)
        VALUES
            ('pool_ai_dev_001', 'AI Developer Staking Pool', '0x1111111111111111', 5.0, 1.5, 0.0, 0, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('pool_blockchain_dev_001', 'Blockchain Developer Staking Pool', '0x2222222222222222', 6.0, 1.8, 0.0, 0, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('pool_fullstack_dev_001', 'Full-Stack Developer Staking Pool', '0x3333333333333333', 4.5, 1.3, 0.0, 0, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)


def downgrade() -> None:
    # Drop tables in reverse order of creation
    op.drop_table("treasury_allocation", if_exists=True)
    op.drop_table("staking_position", if_exists=True)
    op.drop_table("staking_pool", if_exists=True)
    op.drop_table("regional_proposal", if_exists=True)
    op.drop_table("regional_council", if_exists=True)
    op.drop_table("bounty_submission", if_exists=True)
    op.drop_table("bounty_task", if_exists=True)
    op.drop_table("regional_hub", if_exists=True)
    op.drop_table("developer_certification", if_exists=True)
    op.drop_table("developer_profile", if_exists=True)
