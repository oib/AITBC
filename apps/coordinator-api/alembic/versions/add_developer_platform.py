"""Add developer platform and enhanced governance tables

Revision ID: add_developer_platform
Revises: add_global_marketplace
Create Date: 2026-02-28 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_developer_platform'
down_revision = 'add_global_marketplace'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create developer_profile table
    op.create_table(
        'developer_profile',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('wallet_address', sa.String(), nullable=False),
        sa.Column('github_handle', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('reputation_score', sa.Float(), nullable=False, default=0.0),
        sa.Column('total_earned_aitbc', sa.Float(), nullable=False, default=0.0),
        sa.Column('skills', sa.JSON(), nullable=False, default=list),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wallet_address')
    )
    op.create_index('ix_developer_profile_wallet_address', 'developer_profile', ['wallet_address'], unique=False)

    # Create developer_certification table
    op.create_table(
        'developer_certification',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('developer_id', sa.String(), nullable=False),
        sa.Column('certification_name', sa.String(), nullable=False),
        sa.Column('level', sa.String(), nullable=False),
        sa.Column('issued_by', sa.String(), nullable=False),
        sa.Column('ipfs_credential_cid', sa.String(), nullable=True),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('is_valid', sa.Boolean(), nullable=False, default=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['developer_id'], ['developer_profile.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create regional_hub table
    op.create_table(
        'regional_hub',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('manager_address', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_regional_hub_region', 'regional_hub', ['region'], unique=False)

    # Create bounty_task table
    op.create_table(
        'bounty_task',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('required_skills', sa.JSON(), nullable=False, default=list),
        sa.Column('difficulty_level', sa.String(), nullable=False),
        sa.Column('reward_amount', sa.Float(), nullable=False),
        sa.Column('creator_address', sa.String(), nullable=False),
        sa.Column('assigned_developer_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, default='open'),
        sa.Column('deadline', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['assigned_developer_id'], ['developer_profile.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bounty_task_status', 'bounty_task', ['status'], unique=False)
    op.create_index('ix_bounty_task_creator', 'bounty_task', ['creator_address'], unique=False)

    # Create bounty_submission table
    op.create_table(
        'bounty_submission',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('bounty_id', sa.String(), nullable=False),
        sa.Column('developer_id', sa.String(), nullable=False),
        sa.Column('github_pr_url', sa.String(), nullable=True),
        sa.Column('submission_notes', sa.String(), nullable=False, default=''),
        sa.Column('is_approved', sa.Boolean(), nullable=False, default=False),
        sa.Column('review_notes', sa.String(), nullable=True),
        sa.Column('reviewer_address', sa.String(), nullable=True),
        sa.Column('tx_hash_reward', sa.String(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bounty_id'], ['bounty_task.id'], ),
        sa.ForeignKeyConstraint(['developer_id'], ['developer_profile.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bounty_submission_bounty_id', 'bounty_submission', ['bounty_id'], unique=False)
    op.create_index('ix_bounty_submission_developer_id', 'bounty_submission', ['developer_id'], unique=False)

    # Create regional_council table
    op.create_table(
        'regional_council',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('council_name', sa.String(), nullable=False),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('jurisdiction', sa.String(), nullable=False),
        sa.Column('council_members', sa.JSON(), nullable=False, default=list),
        sa.Column('budget_allocation', sa.Float(), nullable=False, default=0.0),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_regional_council_region', 'regional_council', ['region'], unique=False)

    # Create regional_proposal table
    op.create_table(
        'regional_proposal',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('council_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('proposal_type', sa.String(), nullable=False),
        sa.Column('amount_requested', sa.Float(), nullable=False),
        sa.Column('proposer_address', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, default='active'),
        sa.Column('voting_deadline', sa.DateTime(), nullable=False),
        sa.Column('votes_for', sa.Float(), nullable=False, default=0.0),
        sa.Column('votes_against', sa.Float(), nullable=False, default=0.0),
        sa.Column('votes_abstain', sa.Float(), nullable=False, default=0.0),
        sa.Column('total_voting_power', sa.Float(), nullable=False, default=0.0),
        sa.Column('quorum_reached', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['council_id'], ['regional_council.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_regional_proposal_council_id', 'regional_proposal', ['council_id'], unique=False)
    op.create_index('ix_regional_proposal_status', 'regional_proposal', ['status'], unique=False)

    # Create staking_pool table
    op.create_table(
        'staking_pool',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('pool_name', sa.String(), nullable=False),
        sa.Column('developer_address', sa.String(), nullable=False),
        sa.Column('base_apy', sa.Float(), nullable=False),
        sa.Column('reputation_multiplier', sa.Float(), nullable=False),
        sa.Column('total_staked', sa.Float(), nullable=False, default=0.0),
        sa.Column('stakers_count', sa.Integer(), nullable=False, default=0),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_staking_pool_developer_address', 'staking_pool', ['developer_address'], unique=False)

    # Create staking_position table
    op.create_table(
        'staking_position',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('pool_id', sa.String(), nullable=False),
        sa.Column('staker_address', sa.String(), nullable=False),
        sa.Column('amount_staked', sa.Float(), nullable=False),
        sa.Column('apy_at_stake', sa.Float(), nullable=False),
        sa.Column('rewards_earned', sa.Float(), nullable=False, default=0.0),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pool_id'], ['staking_pool.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_staking_position_pool_id', 'staking_position', ['pool_id'], unique=False)
    op.create_index('ix_staking_position_staker_address', 'staking_position', ['staker_address'], unique=False)

    # Create treasury_allocation table
    op.create_table(
        'treasury_allocation',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('council_id', sa.String(), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('purpose', sa.String(), nullable=False),
        sa.Column('recipient_address', sa.String(), nullable=False),
        sa.Column('approver_address', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, default='pending'),
        sa.Column('tx_hash', sa.String(), nullable=True),
        sa.Column('allocated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['council_id'], ['regional_council.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_treasury_allocation_council_id', 'treasury_allocation', ['council_id'], unique=False)
    op.create_index('ix_treasury_allocation_status', 'treasury_allocation', ['status'], unique=False)

    # Insert default data
    # Create sample regional hubs
    op.execute("""
        INSERT INTO regional_hub (id, name, region, description, manager_address, created_at, updated_at)
        VALUES 
            ('hub_us_east_001', 'US Eastern Developer Hub', 'us-east', 'Primary developer hub for US East region', '0x1234567890abcdef', NOW(), NOW()),
            ('hub_eu_west_001', 'EU Western Developer Hub', 'eu-west', 'Primary developer hub for EU West region', '0xabcdef1234567890', NOW(), NOW()),
            ('hub_apac_001', 'Asia-Pacific Developer Hub', 'asia-pacific', 'Primary developer hub for Asia-Pacific region', '0x7890abcdef123456', NOW(), NOW())
    """)

    # Create sample regional councils
    op.execute("""
        INSERT INTO regional_council (id, council_name, region, jurisdiction, council_members, budget_allocation, created_at, updated_at)
        VALUES 
            ('council_us_east_001', 'US Eastern Governance Council', 'us-east', 'United States', 
             '["0x1234567890abcdef", "0x2345678901bcdef", "0x3456789012cdefa"]', 100000.0, NOW(), NOW()),
            ('council_eu_west_001', 'EU Western Governance Council', 'eu-west', 'European Union', 
             '["0xabcdef1234567890", "0xbcdef12345678901", "0xcdef123456789012"]', 80000.0, NOW(), NOW()),
            ('council_apac_001', 'Asia-Pacific Governance Council', 'asia-pacific', 'Singapore', 
             '["0x7890abcdef123456", "0x890abcdef123456", "0x90abcdef1234567"]', 60000.0, NOW(), NOW())
    """)

    # Create sample staking pools
    op.execute("""
        INSERT INTO staking_pool (id, pool_name, developer_address, base_apy, reputation_multiplier, created_at, updated_at)
        VALUES 
            ('pool_ai_dev_001', 'AI Developer Staking Pool', '0x1111111111111111', 5.0, 1.5, NOW(), NOW()),
            ('pool_blockchain_dev_001', 'Blockchain Developer Staking Pool', '0x2222222222222222', 6.0, 1.8, NOW(), NOW()),
            ('pool_fullstack_dev_001', 'Full-Stack Developer Staking Pool', '0x3333333333333333', 4.5, 1.3, NOW(), NOW())
    """)


def downgrade() -> None:
    # Drop tables in reverse order of creation
    op.drop_table('treasury_allocation')
    op.drop_table('staking_position')
    op.drop_table('staking_pool')
    op.drop_table('regional_proposal')
    op.drop_table('regional_council')
    op.drop_table('bounty_submission')
    op.drop_table('bounty_task')
    op.drop_table('regional_hub')
    op.drop_table('developer_certification')
    op.drop_table('developer_profile')
