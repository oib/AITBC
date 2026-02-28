"""Add dynamic pricing tables

Revision ID: add_dynamic_pricing_tables
Revises: initial_migration
Create Date: 2026-02-28 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_dynamic_pricing_tables'
down_revision = 'initial_migration'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create dynamic pricing tables"""
    
    # Create pricing_history table
    op.create_table(
        'pricing_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=False),
        sa.Column('resource_type', sa.Enum('GPU', 'SERVICE', 'STORAGE', 'NETWORK', 'COMPUTE', name='resourcetype'), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('base_price', sa.Float(), nullable=False),
        sa.Column('price_change', sa.Float(), nullable=True),
        sa.Column('price_change_percent', sa.Float(), nullable=True),
        sa.Column('demand_level', sa.Float(), nullable=False),
        sa.Column('supply_level', sa.Float(), nullable=False),
        sa.Column('market_volatility', sa.Float(), nullable=False),
        sa.Column('utilization_rate', sa.Float(), nullable=False),
        sa.Column('strategy_used', sa.Enum('AGGRESSIVE_GROWTH', 'PROFIT_MAXIMIZATION', 'MARKET_BALANCE', 'COMPETITIVE_RESPONSE', 'DEMAND_ELASTICITY', 'PENETRATION_PRICING', 'PREMIUM_PRICING', 'COST_PLUS', 'VALUE_BASED', 'COMPETITOR_BASED', name='pricingstrategytype'), nullable=False),
        sa.Column('strategy_parameters', sa.JSON(), nullable=True),
        sa.Column('pricing_factors', sa.JSON(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('forecast_accuracy', sa.Float(), nullable=True),
        sa.Column('recommendation_followed', sa.Boolean(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('competitor_prices', sa.JSON(), nullable=True),
        sa.Column('market_sentiment', sa.Float(), nullable=False),
        sa.Column('external_factors', sa.JSON(), nullable=True),
        sa.Column('price_reasoning', sa.JSON(), nullable=True),
        sa.Column('audit_log', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_pricing_history_resource_timestamp', 'resource_id', 'timestamp'),
        sa.Index('idx_pricing_history_type_region', 'resource_type', 'region'),
        sa.Index('idx_pricing_history_timestamp', 'timestamp'),
        sa.Index('idx_pricing_history_provider', 'provider_id')
    )
    
    # Create provider_pricing_strategies table
    op.create_table(
        'provider_pricing_strategies',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=False),
        sa.Column('strategy_type', sa.Enum('AGGRESSIVE_GROWTH', 'PROFIT_MAXIMIZATION', 'MARKET_BALANCE', 'COMPETITIVE_RESPONSE', 'DEMAND_ELASTICITY', 'PENETRATION_PRICING', 'PREMIUM_PRICING', 'COST_PLUS', 'VALUE_BASED', 'COMPETITOR_BASED', name='pricingstrategytype'), nullable=False),
        sa.Column('resource_type', sa.Enum('GPU', 'SERVICE', 'STORAGE', 'NETWORK', 'COMPUTE', name='resourcetype'), nullable=True),
        sa.Column('strategy_name', sa.String(), nullable=False),
        sa.Column('strategy_description', sa.String(), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('min_price', sa.Float(), nullable=True),
        sa.Column('max_price', sa.Float(), nullable=True),
        sa.Column('max_change_percent', sa.Float(), nullable=False),
        sa.Column('min_change_interval', sa.Integer(), nullable=False),
        sa.Column('strategy_lock_period', sa.Integer(), nullable=False),
        sa.Column('rules', sa.JSON(), nullable=True),
        sa.Column('custom_conditions', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('auto_optimize', sa.Boolean(), nullable=False),
        sa.Column('learning_enabled', sa.Boolean(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('regions', sa.JSON(), nullable=True),
        sa.Column('global_strategy', sa.Boolean(), nullable=False),
        sa.Column('total_revenue_impact', sa.Float(), nullable=False),
        sa.Column('market_share_impact', sa.Float(), nullable=False),
        sa.Column('customer_satisfaction_impact', sa.Float(), nullable=False),
        sa.Column('strategy_effectiveness_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_applied', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_provider_strategies_provider', 'provider_id'),
        sa.Index('idx_provider_strategies_type', 'strategy_type'),
        sa.Index('idx_provider_strategies_active', 'is_active'),
        sa.Index('idx_provider_strategies_resource', 'resource_type', 'provider_id')
    )
    
    # Create market_metrics table
    op.create_table(
        'market_metrics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('resource_type', sa.Enum('GPU', 'SERVICE', 'STORAGE', 'NETWORK', 'COMPUTE', name='resourcetype'), nullable=False),
        sa.Column('demand_level', sa.Float(), nullable=False),
        sa.Column('supply_level', sa.Float(), nullable=False),
        sa.Column('average_price', sa.Float(), nullable=False),
        sa.Column('price_volatility', sa.Float(), nullable=False),
        sa.Column('utilization_rate', sa.Float(), nullable=False),
        sa.Column('total_capacity', sa.Float(), nullable=False),
        sa.Column('available_capacity', sa.Float(), nullable=False),
        sa.Column('pending_orders', sa.Integer(), nullable=False),
        sa.Column('completed_orders', sa.Integer(), nullable=False),
        sa.Column('order_book_depth', sa.Float(), nullable=False),
        sa.Column('competitor_count', sa.Integer(), nullable=False),
        sa.Column('average_competitor_price', sa.Float(), nullable=False),
        sa.Column('price_spread', sa.Float(), nullable=False),
        sa.Column('market_concentration', sa.Float(), nullable=False),
        sa.Column('market_sentiment', sa.Float(), nullable=False),
        sa.Column('trading_volume', sa.Float(), nullable=False),
        sa.Column('price_momentum', sa.Float(), nullable=False),
        sa.Column('liquidity_score', sa.Float(), nullable=False),
        sa.Column('regional_multiplier', sa.Float(), nullable=False),
        sa.Column('currency_adjustment', sa.Float(), nullable=False),
        sa.Column('regulatory_factors', sa.JSON(), nullable=True),
        sa.Column('data_sources', sa.JSON(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('data_freshness', sa.Integer(), nullable=False),
        sa.Column('completeness_score', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('custom_metrics', sa.JSON(), nullable=True),
        sa.Column('external_factors', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_market_metrics_region_type', 'region', 'resource_type'),
        sa.Index('idx_market_metrics_timestamp', 'timestamp'),
        sa.Index('idx_market_metrics_demand', 'demand_level'),
        sa.Index('idx_market_metrics_supply', 'supply_level'),
        sa.Index('idx_market_metrics_composite', 'region', 'resource_type', 'timestamp')
    )
    
    # Create price_forecasts table
    op.create_table(
        'price_forecasts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=False),
        sa.Column('resource_type', sa.Enum('GPU', 'SERVICE', 'STORAGE', 'NETWORK', 'COMPUTE', name='resourcetype'), nullable=False),
        sa.Column('region', sa.String(), nullable=False),
        sa.Column('forecast_horizon_hours', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(), nullable=False),
        sa.Column('strategy_used', sa.Enum('AGGRESSIVE_GROWTH', 'PROFIT_MAXIMIZATION', 'MARKET_BALANCE', 'COMPETITIVE_RESPONSE', 'DEMAND_ELASTICITY', 'PENETRATION_PRICING', 'PREMIUM_PRICING', 'COST_PLUS', 'VALUE_BASED', 'COMPETITOR_BASED', name='pricingstrategytype'), nullable=False),
        sa.Column('forecast_points', sa.JSON(), nullable=True),
        sa.Column('confidence_intervals', sa.JSON(), nullable=True),
        sa.Column('average_forecast_price', sa.Float(), nullable=False),
        sa.Column('price_range_forecast', sa.JSON(), nullable=True),
        sa.Column('trend_forecast', sa.Enum('INCREASING', 'DECREASING', 'STABLE', 'VOLATILE', 'UNKNOWN', name='pricetrend'), nullable=False),
        sa.Column('volatility_forecast', sa.Float(), nullable=False),
        sa.Column('model_confidence', sa.Float(), nullable=False),
        sa.Column('accuracy_score', sa.Float(), nullable=True),
        sa.Column('mean_absolute_error', sa.Float(), nullable=True),
        sa.Column('mean_absolute_percentage_error', sa.Float(), nullable=True),
        sa.Column('input_data_summary', sa.JSON(), nullable=True),
        sa.Column('market_conditions_at_forecast', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('target_timestamp', sa.DateTime(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(), nullable=True),
        sa.Column('forecast_status', sa.String(), nullable=False),
        sa.Column('outcome', sa.String(), nullable=True),
        sa.Column('lessons_learned', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_price_forecasts_resource', 'resource_id'),
        sa.Index('idx_price_forecasts_target', 'target_timestamp'),
        sa.Index('idx_price_forecasts_created', 'created_at'),
        sa.Index('idx_price_forecasts_horizon', 'forecast_horizon_hours')
    )
    
    # Create pricing_optimizations table
    op.create_table(
        'pricing_optimizations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('experiment_id', sa.String(), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=False),
        sa.Column('resource_type', sa.Enum('GPU', 'SERVICE', 'STORAGE', 'NETWORK', 'COMPUTE', name='resourcetype'), nullable=True),
        sa.Column('experiment_name', sa.String(), nullable=False),
        sa.Column('experiment_type', sa.String(), nullable=False),
        sa.Column('hypothesis', sa.String(), nullable=False),
        sa.Column('control_strategy', sa.Enum('AGGRESSIVE_GROWTH', 'PROFIT_MAXIMIZATION', 'MARKET_BALANCE', 'COMPETITIVE_RESPONSE', 'DEMAND_ELASTICITY', 'PENETRATION_PRICING', 'PREMIUM_PRICING', 'COST_PLUS', 'VALUE_BASED', 'COMPETITOR_BASED', name='pricingstrategytype'), nullable=False),
        sa.Column('test_strategy', sa.Enum('AGGRESSIVE_GROWTH', 'PROFIT_MAXIMIZATION', 'MARKET_BALANCE', 'COMPETITIVE_RESPONSE', 'DEMAND_ELASTICITY', 'PENETRATION_PRICING', 'PREMIUM_PRICING', 'COST_PLUS', 'VALUE_BASED', 'COMPETITOR_BASED', name='pricingstrategytype'), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('confidence_level', sa.Float(), nullable=False),
        sa.Column('statistical_power', sa.Float(), nullable=False),
        sa.Column('minimum_detectable_effect', sa.Float(), nullable=False),
        sa.Column('regions', sa.JSON(), nullable=True),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('control_performance', sa.JSON(), nullable=True),
        sa.Column('test_performance', sa.JSON(), nullable=True),
        sa.Column('statistical_significance', sa.Float(), nullable=True),
        sa.Column('effect_size', sa.Float(), nullable=True),
        sa.Column('revenue_impact', sa.Float(), nullable=True),
        sa.Column('profit_impact', sa.Float(), nullable=True),
        sa.Column('market_share_impact', sa.Float(), nullable=True),
        sa.Column('customer_satisfaction_impact', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('conclusion', sa.String(), nullable=True),
        sa.Column('recommendations', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_pricing_opt_provider', 'provider_id'),
        sa.Index('idx_pricing_opt_experiment', 'experiment_id'),
        sa.Index('idx_pricing_opt_status', 'status'),
        sa.Index('idx_pricing_opt_created', 'created_at')
    )
    
    # Create pricing_alerts table
    op.create_table(
        'pricing_alerts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=True),
        sa.Column('resource_id', sa.String(), nullable=True),
        sa.Column('resource_type', sa.Enum('GPU', 'SERVICE', 'STORAGE', 'NETWORK', 'COMPUTE', name='resourcetype'), nullable=True),
        sa.Column('alert_type', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('trigger_conditions', sa.JSON(), nullable=True),
        sa.Column('threshold_values', sa.JSON(), nullable=True),
        sa.Column('actual_values', sa.JSON(), nullable=True),
        sa.Column('market_conditions', sa.JSON(), nullable=True),
        sa.Column('strategy_context', sa.JSON(), nullable=True),
        sa.Column('historical_context', sa.JSON(), nullable=True),
        sa.Column('recommendations', sa.JSON(), nullable=True),
        sa.Column('automated_actions_taken', sa.JSON(), nullable=True),
        sa.Column('manual_actions_required', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('resolution', sa.String(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('business_impact', sa.String(), nullable=True),
        sa.Column('revenue_impact_estimate', sa.Float(), nullable=True),
        sa.Column('customer_impact_estimate', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('notification_sent', sa.Boolean(), nullable=False),
        sa.Column('notification_channels', sa.JSON(), nullable=True),
        sa.Column('escalation_level', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_pricing_alerts_provider', 'provider_id'),
        sa.Index('idx_pricing_alerts_type', 'alert_type'),
        sa.Index('idx_pricing_alerts_status', 'status'),
        sa.Index('idx_pricing_alerts_severity', 'severity'),
        sa.Index('idx_pricing_alerts_created', 'created_at')
    )
    
    # Create pricing_rules table
    op.create_table(
        'pricing_rules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=True),
        sa.Column('strategy_id', sa.String(), nullable=True),
        sa.Column('rule_name', sa.String(), nullable=False),
        sa.Column('rule_description', sa.String(), nullable=True),
        sa.Column('rule_type', sa.String(), nullable=False),
        sa.Column('condition_expression', sa.String(), nullable=False),
        sa.Column('action_expression', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('resource_types', sa.JSON(), nullable=True),
        sa.Column('regions', sa.JSON(), nullable=True),
        sa.Column('time_conditions', sa.JSON(), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('thresholds', sa.JSON(), nullable=True),
        sa.Column('multipliers', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('execution_count', sa.Integer(), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False),
        sa.Column('failure_count', sa.Integer(), nullable=False),
        sa.Column('last_executed', sa.DateTime(), nullable=True),
        sa.Column('last_success', sa.DateTime(), nullable=True),
        sa.Column('average_execution_time', sa.Float(), nullable=True),
        sa.Column('success_rate', sa.Float(), nullable=False),
        sa.Column('business_impact', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('change_log', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_pricing_rules_provider', 'provider_id'),
        sa.Index('idx_pricing_rules_strategy', 'strategy_id'),
        sa.Index('idx_pricing_rules_active', 'is_active'),
        sa.Index('idx_pricing_rules_priority', 'priority')
    )
    
    # Create pricing_audit_log table
    op.create_table(
        'pricing_audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('provider_id', sa.String(), nullable=True),
        sa.Column('resource_id', sa.String(), nullable=True),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('action_description', sa.String(), nullable=False),
        sa.Column('action_source', sa.String(), nullable=False),
        sa.Column('before_state', sa.JSON(), nullable=True),
        sa.Column('after_state', sa.JSON(), nullable=True),
        sa.Column('changed_fields', sa.JSON(), nullable=True),
        sa.Column('decision_reasoning', sa.Text(), nullable=True),
        sa.Column('market_conditions', sa.JSON(), nullable=True),
        sa.Column('business_context', sa.JSON(), nullable=True),
        sa.Column('immediate_impact', sa.JSON(), nullable=True),
        sa.Column('expected_impact', sa.JSON(), nullable=True),
        sa.Column('actual_impact', sa.JSON(), nullable=True),
        sa.Column('compliance_flags', sa.JSON(), nullable=True),
        sa.Column('approval_required', sa.Boolean(), nullable=False),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('api_endpoint', sa.String(), nullable=True),
        sa.Column('request_id', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_pricing_audit_provider', 'provider_id'),
        sa.Index('idx_pricing_audit_resource', 'resource_id'),
        sa.Index('idx_pricing_audit_action', 'action_type'),
        sa.Index('idx_pricing_audit_timestamp', 'timestamp'),
        sa.Index('idx_pricing_audit_user', 'user_id')
    )


def downgrade() -> None:
    """Drop dynamic pricing tables"""
    
    # Drop tables in reverse order of creation
    op.drop_table('pricing_audit_log')
    op.drop_table('pricing_rules')
    op.drop_table('pricing_alerts')
    op.drop_table('pricing_optimizations')
    op.drop_table('price_forecasts')
    op.drop_table('market_metrics')
    op.drop_table('provider_pricing_strategies')
    op.drop_table('pricing_history')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS pricetrend')
    op.execute('DROP TYPE IF EXISTS pricingstrategytype')
    op.execute('DROP TYPE IF EXISTS resourcetype')
