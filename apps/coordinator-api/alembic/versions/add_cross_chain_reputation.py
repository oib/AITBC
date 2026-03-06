"""Add cross-chain reputation system tables

Revision ID: add_cross_chain_reputation
Revises: add_dynamic_pricing_tables
Create Date: 2026-02-28 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_cross_chain_reputation'
down_revision = 'add_dynamic_pricing_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create cross-chain reputation system tables"""
    
    # Create cross_chain_reputation_configs table
    op.create_table(
        'cross_chain_reputation_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('chain_id', sa.Integer(), nullable=False),
        sa.Column('chain_weight', sa.Float(), nullable=False),
        sa.Column('base_reputation_bonus', sa.Float(), nullable=False),
        sa.Column('transaction_success_weight', sa.Float(), nullable=False),
        sa.Column('transaction_failure_weight', sa.Float(), nullable=False),
        sa.Column('dispute_penalty_weight', sa.Float(), nullable=False),
        sa.Column('minimum_transactions_for_score', sa.Integer(), nullable=False),
        sa.Column('reputation_decay_rate', sa.Float(), nullable=False),
        sa.Column('anomaly_detection_threshold', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('configuration_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chain_id')
    )
    op.create_index('idx_chain_reputation_config_chain', 'cross_chain_reputation_configs', ['chain_id'])
    op.create_index('idx_chain_reputation_config_active', 'cross_chain_reputation_configs', ['is_active'])
    
    # Create cross_chain_reputation_aggregations table
    op.create_table(
        'cross_chain_reputation_aggregations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('aggregated_score', sa.Float(), nullable=False),
        sa.Column('weighted_score', sa.Float(), nullable=False),
        sa.Column('normalized_score', sa.Float(), nullable=False),
        sa.Column('chain_count', sa.Integer(), nullable=False),
        sa.Column('active_chains', sa.JSON(), nullable=True),
        sa.Column('chain_scores', sa.JSON(), nullable=True),
        sa.Column('chain_weights', sa.JSON(), nullable=True),
        sa.Column('score_variance', sa.Float(), nullable=False),
        sa.Column('score_range', sa.Float(), nullable=False),
        sa.Column('consistency_score', sa.Float(), nullable=False),
        sa.Column('verification_status', sa.String(), nullable=False),
        sa.Column('verification_details', sa.JSON(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cross_chain_agg_agent', 'cross_chain_reputation_aggregations', ['agent_id'])
    op.create_index('idx_cross_chain_agg_score', 'cross_chain_reputation_aggregations', ['aggregated_score'])
    op.create_index('idx_cross_chain_agg_updated', 'cross_chain_reputation_aggregations', ['last_updated'])
    op.create_index('idx_cross_chain_agg_status', 'cross_chain_reputation_aggregations', ['verification_status'])
    
    # Create cross_chain_reputation_events table
    op.create_table(
        'cross_chain_reputation_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('source_chain_id', sa.Integer(), nullable=False),
        sa.Column('target_chain_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('impact_score', sa.Float(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('source_reputation', sa.Float(), nullable=True),
        sa.Column('target_reputation', sa.Float(), nullable=True),
        sa.Column('reputation_change', sa.Float(), nullable=True),
        sa.Column('event_data', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cross_chain_event_agent', 'cross_chain_reputation_events', ['agent_id'])
    op.create_index('idx_cross_chain_event_chains', 'cross_chain_reputation_events', ['source_chain_id', 'target_chain_id'])
    op.create_index('idx_cross_chain_event_type', 'cross_chain_reputation_events', ['event_type'])
    op.create_index('idx_cross_chain_event_created', 'cross_chain_reputation_events', ['created_at'])
    
    # Create reputation_metrics table
    op.create_table(
        'reputation_metrics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('chain_id', sa.Integer(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('total_agents', sa.Integer(), nullable=False),
        sa.Column('average_reputation', sa.Float(), nullable=False),
        sa.Column('reputation_distribution', sa.JSON(), nullable=True),
        sa.Column('total_transactions', sa.Integer(), nullable=False),
        sa.Column('success_rate', sa.Float(), nullable=False),
        sa.Column('dispute_rate', sa.Float(), nullable=False),
        sa.Column('level_distribution', sa.JSON(), nullable=True),
        sa.Column('score_distribution', sa.JSON(), nullable=True),
        sa.Column('cross_chain_agents', sa.Integer(), nullable=False),
        sa.Column('average_consistency_score', sa.Float(), nullable=False),
        sa.Column('chain_diversity_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_reputation_metrics_chain_date', 'reputation_metrics', ['chain_id', 'metric_date'])
    op.create_index('idx_reputation_metrics_date', 'reputation_metrics', ['metric_date'])


def downgrade() -> None:
    """Drop cross-chain reputation system tables"""
    
    # Drop tables in reverse order
    op.drop_table('reputation_metrics')
    op.drop_table('cross_chain_reputation_events')
    op.drop_table('cross_chain_reputation_aggregations')
    op.drop_table('cross_chain_reputation_configs')
