"""Add global marketplace tables

Revision ID: add_global_marketplace
Revises: add_cross_chain_reputation
Create Date: 2026-02-28 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_global_marketplace'
down_revision = 'add_cross_chain_reputation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create global marketplace tables"""
    
    # Create marketplace_regions table
    op.create_table(
        'marketplace_regions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('region_code', sa.String(), nullable=False),
        sa.Column('region_name', sa.String(), nullable=False),
        sa.Column('geographic_area', sa.String(), nullable=False),
        sa.Column('base_currency', sa.String(), nullable=False),
        sa.Column('timezone', sa.String(), nullable=False),
        sa.Column('language', sa.String(), nullable=False),
        sa.Column('load_factor', sa.Float(), nullable=False),
        sa.Column('max_concurrent_requests', sa.Integer(), nullable=False),
        sa.Column('priority_weight', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('health_score', sa.Float(), nullable=False),
        sa.Column('last_health_check', sa.DateTime(), nullable=True),
        sa.Column('api_endpoint', sa.String(), nullable=False),
        sa.Column('websocket_endpoint', sa.String(), nullable=False),
        sa.Column('blockchain_rpc_endpoints', sa.JSON(), nullable=True),
        sa.Column('average_response_time', sa.Float(), nullable=False),
        sa.Column('request_rate', sa.Float(), nullable=False),
        sa.Column('error_rate', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('region_code')
    )
    op.create_index('idx_marketplace_region_code', 'marketplace_regions', ['region_code'])
    op.create_index('idx_marketplace_region_status', 'marketplace_regions', ['status'])
    op.create_index('idx_marketplace_region_health', 'marketplace_regions', ['health_score'])
    
    # Create global_marketplace_configs table
    op.create_table(
        'global_marketplace_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('config_key', sa.String(), nullable=False),
        sa.Column('config_value', sa.String(), nullable=True),
        sa.Column('config_type', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False),
        sa.Column('min_value', sa.Float(), nullable=True),
        sa.Column('max_value', sa.Float(), nullable=True),
        sa.Column('allowed_values', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_modified_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_key')
    )
    op.create_index('idx_global_config_key', 'global_marketplace_configs', ['config_key'])
    op.create_index('idx_global_config_category', 'global_marketplace_configs', ['category'])
    
    # Create global_marketplace_offers table
    op.create_table(
        'global_marketplace_offers',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('original_offer_id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('service_type', sa.String(), nullable=False),
        sa.Column('resource_specification', sa.JSON(), nullable=True),
        sa.Column('base_price', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('price_per_region', sa.JSON(), nullable=True),
        sa.Column('dynamic_pricing_enabled', sa.Boolean(), nullable=False),
        sa.Column('total_capacity', sa.Integer(), nullable=False),
        sa.Column('available_capacity', sa.Integer(), nullable=False),
        sa.Column('regions_available', sa.JSON(), nullable=True),
        sa.Column('global_status', sa.String(), nullable=False),
        sa.Column('region_statuses', sa.JSON(), nullable=True),
        sa.Column('global_rating', sa.Float(), nullable=False),
        sa.Column('total_transactions', sa.Integer(), nullable=False),
        sa.Column('success_rate', sa.Float(), nullable=False),
        sa.Column('supported_chains', sa.JSON(), nullable=True),
        sa.Column('cross_chain_pricing', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_global_offer_agent', 'global_marketplace_offers', ['agent_id'])
    op.create_index('idx_global_offer_service', 'global_marketplace_offers', ['service_type'])
    op.create_index('idx_global_offer_status', 'global_marketplace_offers', ['global_status'])
    op.create_index('idx_global_offer_created', 'global_marketplace_offers', ['created_at'])
    
    # Create global_marketplace_transactions table
    op.create_table(
        'global_marketplace_transactions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('transaction_hash', sa.String(), nullable=True),
        sa.Column('buyer_id', sa.String(), nullable=False),
        sa.Column('seller_id', sa.String(), nullable=False),
        sa.Column('offer_id', sa.String(), nullable=False),
        sa.Column('service_type', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('source_chain', sa.Integer(), nullable=True),
        sa.Column('target_chain', sa.Integer(), nullable=True),
        sa.Column('bridge_transaction_id', sa.String(), nullable=True),
        sa.Column('cross_chain_fee', sa.Float(), nullable=False),
        sa.Column('source_region', sa.String(), nullable=False),
        sa.Column('target_region', sa.String(), nullable=False),
        sa.Column('regional_fees', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('payment_status', sa.String(), nullable=False),
        sa.Column('delivery_status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_global_tx_buyer', 'global_marketplace_transactions', ['buyer_id'])
    op.create_index('idx_global_tx_seller', 'global_marketplace_transactions', ['seller_id'])
    op.create_index('idx_global_tx_offer', 'global_marketplace_transactions', ['offer_id'])
    op.create_index('idx_global_tx_status', 'global_marketplace_transactions', ['status'])
    op.create_index('idx_global_tx_created', 'global_marketplace_transactions', ['created_at'])
    op.create_index('idx_global_tx_chain', 'global_marketplace_transactions', ['source_chain', 'target_chain'])
    
    # Create global_marketplace_analytics table
    op.create_table(
        'global_marketplace_analytics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('period_type', sa.String(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('total_offers', sa.Integer(), nullable=False),
        sa.Column('total_transactions', sa.Integer(), nullable=False),
        sa.Column('total_volume', sa.Float(), nullable=False),
        sa.Column('average_price', sa.Float(), nullable=False),
        sa.Column('average_response_time', sa.Float(), nullable=False),
        sa.Column('success_rate', sa.Float(), nullable=False),
        sa.Column('error_rate', sa.Float(), nullable=False),
        sa.Column('active_buyers', sa.Integer(), nullable=False),
        sa.Column('active_sellers', sa.Integer(), nullable=False),
        sa.Column('new_users', sa.Integer(), nullable=False),
        sa.Column('cross_chain_transactions', sa.Integer(), nullable=False),
        sa.Column('cross_chain_volume', sa.Float(), nullable=False),
        sa.Column('supported_chains', sa.JSON(), nullable=True),
        sa.Column('regional_distribution', sa.JSON(), nullable=True),
        sa.Column('regional_performance', sa.JSON(), nullable=True),
        sa.Column('analytics_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_global_analytics_period', 'global_marketplace_analytics', ['period_type', 'period_start'])
    op.create_index('idx_global_analytics_region', 'global_marketplace_analytics', ['region'])
    op.create_index('idx_global_analytics_created', 'global_marketplace_analytics', ['created_at'])
    
    # Create global_marketplace_governance table
    op.create_table(
        'global_marketplace_governance',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rule_type', sa.String(), nullable=False),
        sa.Column('rule_name', sa.String(), nullable=False),
        sa.Column('rule_description', sa.String(), nullable=False),
        sa.Column('rule_parameters', sa.JSON(), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('global_scope', sa.Boolean(), nullable=False),
        sa.Column('applicable_regions', sa.JSON(), nullable=True),
        sa.Column('applicable_services', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('enforcement_level', sa.String(), nullable=False),
        sa.Column('penalty_parameters', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('effective_from', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_global_gov_rule_type', 'global_marketplace_governance', ['rule_type'])
    op.create_index('idx_global_gov_active', 'global_marketplace_governance', ['is_active'])
    op.create_index('idx_global_gov_effective', 'global_marketplace_governance', ['effective_from', 'expires_at'])
    
    # Insert default regions
    op.execute("""
        INSERT INTO marketplace_regions (id, region_code, region_name, geographic_area, base_currency, timezone, language, load_factor, max_concurrent_requests, priority_weight, status, health_score, api_endpoint, websocket_endpoint, created_at, updated_at)
        VALUES 
        ('region_us_east_1', 'us-east-1', 'US East (N. Virginia)', 'north_america', 'USD', 'UTC', 'en', 1.0, 1000, 1.0, 'active', 1.0, 'https://api.aitbc.dev/v1', 'wss://ws.aitbc.dev/v1', NOW(), NOW()),
        ('region_us_west_1', 'us-west-1', 'US West (N. California)', 'north_america', 'USD', 'UTC', 'en', 1.0, 1000, 1.0, 'active', 1.0, 'https://api.aitbc.dev/v1', 'wss://ws.aitbc.dev/v1', NOW(), NOW()),
        ('region_eu_west_1', 'eu-west-1', 'EU West (Ireland)', 'europe', 'EUR', 'UTC', 'en', 1.0, 1000, 1.0, 'active', 1.0, 'https://api.aitbc.dev/v1', 'wss://ws.aitbc.dev/v1', NOW(), NOW()),
        ('region_ap_south_1', 'ap-south-1', 'AP South (Mumbai)', 'asia_pacific', 'USD', 'UTC', 'en', 1.0, 1000, 1.0, 'active', 1.0, 'https://api.aitbc.dev/v1', 'wss://ws.aitbc.dev/v1', NOW(), NOW())
    """)
    
    # Insert default global marketplace configurations
    op.execute("""
        INSERT INTO global_marketplace_configs (id, config_key, config_value, config_type, description, category, is_public, created_at, updated_at)
        VALUES 
        ('config_global_enabled', 'global_enabled', 'true', 'boolean', 'Enable global marketplace functionality', 'general', true, NOW(), NOW()),
        ('config_max_regions_per_offer', 'max_regions_per_offer', '10', 'number', 'Maximum number of regions per offer', 'limits', false, NOW(), NOW()),
        ('config_default_currency', 'default_currency', 'USD', 'string', 'Default currency for global marketplace', 'general', true, NOW(), NOW()),
        ('config_cross_chain_enabled', 'cross_chain_enabled', 'true', 'boolean', 'Enable cross-chain transactions', 'cross_chain', true, NOW(), NOW()),
        ('config_min_reputation_global', 'min_reputation_global', '500', 'number', 'Minimum reputation for global marketplace', 'reputation', false, NOW(), NOW())
    """)


def downgrade() -> None:
    """Drop global marketplace tables"""
    
    # Drop tables in reverse order
    op.drop_table('global_marketplace_governance')
    op.drop_table('global_marketplace_analytics')
    op.drop_table('global_marketplace_transactions')
    op.drop_table('global_marketplace_offers')
    op.drop_table('global_marketplace_configs')
    op.drop_table('marketplace_regions')
