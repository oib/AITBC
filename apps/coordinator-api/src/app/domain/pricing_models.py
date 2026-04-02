"""
Pricing Models for Dynamic Pricing Database Schema
SQLModel definitions for pricing history, strategies, and market metrics
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel, Text


class PricingStrategyType(StrEnum):
    """Pricing strategy types for database"""

    AGGRESSIVE_GROWTH = "aggressive_growth"
    PROFIT_MAXIMIZATION = "profit_maximization"
    MARKET_BALANCE = "market_balance"
    COMPETITIVE_RESPONSE = "competitive_response"
    DEMAND_ELASTICITY = "demand_elasticity"
    PENETRATION_PRICING = "penetration_pricing"
    PREMIUM_PRICING = "premium_pricing"
    COST_PLUS = "cost_plus"
    VALUE_BASED = "value_based"
    COMPETITOR_BASED = "competitor_based"


class ResourceType(StrEnum):
    """Resource types for pricing"""

    GPU = "gpu"
    SERVICE = "service"
    STORAGE = "storage"
    NETWORK = "network"
    COMPUTE = "compute"


class PriceTrend(StrEnum):
    """Price trend indicators"""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class PricingHistory(SQLModel, table=True):
    """Historical pricing data for analysis and machine learning"""

    __tablename__ = "pricing_history"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_pricing_history_resource_timestamp", "resource_id", "timestamp"),)
#    #        # Index(        Index("idx_pricing_history_type_region", "resource_type", "region"),)
#    #        # Index(        Index("idx_pricing_history_timestamp", "timestamp"),)
#    #        # Index(        Index("idx_pricing_history_provider", "provider_id"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"ph_{uuid4().hex[:12]}", primary_key=True)
    resource_id: str = Field(index=True)
    resource_type: ResourceType = Field(index=True)
    provider_id: str | None = Field(default=None, index=True)
    region: str = Field(default="global", index=True)

    # Pricing data
    price: float = Field(index=True)
    base_price: float
    price_change: float | None = None  # Change from previous price
    price_change_percent: float | None = None  # Percentage change

    # Market conditions at time of pricing
    demand_level: float = Field(index=True)
    supply_level: float = Field(index=True)
    market_volatility: float
    utilization_rate: float

    # Strategy and factors
    strategy_used: PricingStrategyType = Field(index=True)
    strategy_parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    pricing_factors: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Performance metrics
    confidence_score: float
    forecast_accuracy: float | None = None
    recommendation_followed: bool | None = None

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional context
    competitor_prices: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    market_sentiment: float = Field(default=0.0)
    external_factors: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Reasoning and audit trail
    price_reasoning: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    audit_log: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ProviderPricingStrategy(SQLModel, table=True):
    """Provider pricing strategies and configurations"""

    __tablename__ = "provider_pricing_strategies"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_provider_strategies_provider", "provider_id"),)
#    #        # Index(        Index("idx_provider_strategies_type", "strategy_type"),)
#    #        # Index(        Index("idx_provider_strategies_active", "is_active"),)
#    #        # Index(        Index("idx_provider_strategies_resource", "resource_type", "provider_id"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"pps_{uuid4().hex[:12]}", primary_key=True)
    provider_id: str = Field(index=True)
    strategy_type: PricingStrategyType = Field(index=True)
    resource_type: ResourceType | None = Field(default=None, index=True)

    # Strategy configuration
    strategy_name: str
    strategy_description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Constraints and limits
    min_price: float | None = None
    max_price: float | None = None
    max_change_percent: float = Field(default=0.5)
    min_change_interval: int = Field(default=300)  # seconds
    strategy_lock_period: int = Field(default=3600)  # seconds

    # Strategy rules
    rules: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    custom_conditions: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Status and metadata
    is_active: bool = Field(default=True, index=True)
    auto_optimize: bool = Field(default=True)
    learning_enabled: bool = Field(default=True)
    priority: int = Field(default=5)  # 1-10 priority level

    # Geographic scope
    regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    global_strategy: bool = Field(default=True)

    # Performance tracking
    total_revenue_impact: float = Field(default=0.0)
    market_share_impact: float = Field(default=0.0)
    customer_satisfaction_impact: float = Field(default=0.0)
    strategy_effectiveness_score: float = Field(default=0.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_applied: datetime | None = None
    expires_at: datetime | None = None

    # Audit information
    created_by: str | None = None
    updated_by: str | None = None
    version: int = Field(default=1)


class MarketMetrics(SQLModel, table=True):
    """Real-time and historical market metrics"""

    __tablename__ = "market_metrics"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_market_metrics_region_type", "region", "resource_type"),)
#    #        # Index(        Index("idx_market_metrics_timestamp", "timestamp"),)
#    #        # Index(        Index("idx_market_metrics_demand", "demand_level"),)
#    #        # Index(        Index("idx_market_metrics_supply", "supply_level"),)
#    #        # Index(        Index("idx_market_metrics_composite", "region", "resource_type", "timestamp"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"mm_{uuid4().hex[:12]}", primary_key=True)
    region: str = Field(index=True)
    resource_type: ResourceType = Field(index=True)

    # Core market metrics
    demand_level: float = Field(index=True)
    supply_level: float = Field(index=True)
    average_price: float = Field(index=True)
    price_volatility: float = Field(index=True)
    utilization_rate: float = Field(index=True)

    # Market depth and liquidity
    total_capacity: float
    available_capacity: float
    pending_orders: int
    completed_orders: int
    order_book_depth: float

    # Competitive landscape
    competitor_count: int
    average_competitor_price: float
    price_spread: float  # Difference between highest and lowest prices
    market_concentration: float  # HHI or similar metric

    # Market sentiment and activity
    market_sentiment: float = Field(default=0.0)
    trading_volume: float
    price_momentum: float  # Rate of price change
    liquidity_score: float

    # Regional factors
    regional_multiplier: float = Field(default=1.0)
    currency_adjustment: float = Field(default=1.0)
    regulatory_factors: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Data quality and confidence
    data_sources: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    confidence_score: float
    data_freshness: int  # Age of data in seconds
    completeness_score: float

    # Timestamps
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional metrics
    custom_metrics: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    external_factors: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class PriceForecast(SQLModel, table=True):
    """Price forecasting data and accuracy tracking"""

    __tablename__ = "price_forecasts"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_price_forecasts_resource", "resource_id"),)
#    #        # Index(        Index("idx_price_forecasts_target", "target_timestamp"),)
#    #        # Index(        Index("idx_price_forecasts_created", "created_at"),)
#    #        # Index(        Index("idx_price_forecasts_horizon", "forecast_horizon_hours"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"pf_{uuid4().hex[:12]}", primary_key=True)
    resource_id: str = Field(index=True)
    resource_type: ResourceType = Field(index=True)
    region: str = Field(default="global", index=True)

    # Forecast parameters
    forecast_horizon_hours: int = Field(index=True)
    model_version: str
    strategy_used: PricingStrategyType

    # Forecast data points
    forecast_points: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    confidence_intervals: dict[str, list[float]] = Field(default_factory=dict, sa_column=Column(JSON))

    # Forecast metadata
    average_forecast_price: float
    price_range_forecast: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    trend_forecast: PriceTrend
    volatility_forecast: float

    # Model performance
    model_confidence: float
    accuracy_score: float | None = None  # Populated after actual prices are known
    mean_absolute_error: float | None = None
    mean_absolute_percentage_error: float | None = None

    # Input data used for forecast
    input_data_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    market_conditions_at_forecast: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    target_timestamp: datetime = Field(index=True)  # When forecast is for
    evaluated_at: datetime | None = None  # When forecast was evaluated

    # Status and outcomes
    forecast_status: str = Field(default="pending")  # pending, evaluated, expired
    outcome: str | None = None  # accurate, inaccurate, mixed
    lessons_learned: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class PricingOptimization(SQLModel, table=True):
    """Pricing optimization experiments and results"""

    __tablename__ = "pricing_optimizations"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_pricing_opt_provider", "provider_id"),)
#    #        # Index(        Index("idx_pricing_opt_experiment", "experiment_id"),)
#    #        # Index(        Index("idx_pricing_opt_status", "status"),)
#    #        # Index(        Index("idx_pricing_opt_created", "created_at"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"po_{uuid4().hex[:12]}", primary_key=True)
    experiment_id: str = Field(index=True)
    provider_id: str = Field(index=True)
    resource_type: ResourceType | None = Field(default=None, index=True)

    # Experiment configuration
    experiment_name: str
    experiment_type: str  # ab_test, multivariate, optimization
    hypothesis: str
    control_strategy: PricingStrategyType
    test_strategy: PricingStrategyType

    # Experiment parameters
    sample_size: int
    confidence_level: float = Field(default=0.95)
    statistical_power: float = Field(default=0.8)
    minimum_detectable_effect: float

    # Experiment scope
    regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    duration_days: int
    start_date: datetime
    end_date: datetime | None = None

    # Results
    control_performance: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    test_performance: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    statistical_significance: float | None = None
    effect_size: float | None = None

    # Business impact
    revenue_impact: float | None = None
    profit_impact: float | None = None
    market_share_impact: float | None = None
    customer_satisfaction_impact: float | None = None

    # Status and metadata
    status: str = Field(default="planned")  # planned, running, completed, failed
    conclusion: str | None = None
    recommendations: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # Audit trail
    created_by: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None


class PricingAlert(SQLModel, table=True):
    """Pricing alerts and notifications"""

    __tablename__ = "pricing_alerts"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_pricing_alerts_provider", "provider_id"),)
#    #        # Index(        Index("idx_pricing_alerts_type", "alert_type"),)
#    #        # Index(        Index("idx_pricing_alerts_status", "status"),)
#    #        # Index(        Index("idx_pricing_alerts_severity", "severity"),)
#    #        # Index(        Index("idx_pricing_alerts_created", "created_at"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"pa_{uuid4().hex[:12]}", primary_key=True)
    provider_id: str | None = Field(default=None, index=True)
    resource_id: str | None = Field(default=None, index=True)
    resource_type: ResourceType | None = Field(default=None, index=True)

    # Alert details
    alert_type: str = Field(index=True)  # price_volatility, strategy_performance, market_change, etc.
    severity: str = Field(index=True)  # low, medium, high, critical
    title: str
    description: str

    # Alert conditions
    trigger_conditions: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    threshold_values: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    actual_values: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Alert context
    market_conditions: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    strategy_context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    historical_context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Recommendations and actions
    recommendations: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    automated_actions_taken: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    manual_actions_required: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Status and resolution
    status: str = Field(default="active")  # active, acknowledged, resolved, dismissed
    resolution: str | None = None
    resolution_notes: str | None = Field(default=None, sa_column=Text)

    # Impact assessment
    business_impact: str | None = None
    revenue_impact_estimate: float | None = None
    customer_impact_estimate: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    # Communication
    notification_sent: bool = Field(default=False)
    notification_channels: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    escalation_level: int = Field(default=0)


class PricingRule(SQLModel, table=True):
    """Custom pricing rules and conditions"""

    __tablename__ = "pricing_rules"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_pricing_rules_provider", "provider_id"),)
#    #        # Index(        Index("idx_pricing_rules_strategy", "strategy_id"),)
#    #        # Index(        Index("idx_pricing_rules_active", "is_active"),)
#    #        # Index(        Index("idx_pricing_rules_priority", "priority"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"pr_{uuid4().hex[:12]}", primary_key=True)
    provider_id: str | None = Field(default=None, index=True)
    strategy_id: str | None = Field(default=None, index=True)

    # Rule definition
    rule_name: str
    rule_description: str | None = None
    rule_type: str  # condition, action, constraint, optimization

    # Rule logic
    condition_expression: str = Field(..., description="Logical condition for rule")
    action_expression: str = Field(..., description="Action to take when condition is met")
    priority: int = Field(default=5, index=True)  # 1-10 priority

    # Rule scope
    resource_types: list[ResourceType] = Field(default_factory=list, sa_column=Column(JSON))
    regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    time_conditions: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Rule parameters
    parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    thresholds: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    multipliers: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Status and execution
    is_active: bool = Field(default=True, index=True)
    execution_count: int = Field(default=0)
    success_count: int = Field(default=0)
    failure_count: int = Field(default=0)
    last_executed: datetime | None = None
    last_success: datetime | None = None

    # Performance metrics
    average_execution_time: float | None = None
    success_rate: float = Field(default=1.0)
    business_impact: float | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    # Audit trail
    created_by: str | None = None
    updated_by: str | None = None
    version: int = Field(default=1)
    change_log: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class PricingAuditLog(SQLModel, table=True):
    """Audit log for pricing changes and decisions"""

    __tablename__ = "pricing_audit_log"
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_pricing_audit_provider", "provider_id"),)
#    #        # Index(        Index("idx_pricing_audit_resource", "resource_id"),)
#    #        # Index(        Index("idx_pricing_audit_action", "action_type"),)
#    #        # Index(        Index("idx_pricing_audit_timestamp", "timestamp"),)
#    #        # Index(        Index("idx_pricing_audit_user", "user_id"),)
###        ],
    }

    id: str = Field(default_factory=lambda: f"pal_{uuid4().hex[:12]}", primary_key=True)
    provider_id: str | None = Field(default=None, index=True)
    resource_id: str | None = Field(default=None, index=True)
    user_id: str | None = Field(default=None, index=True)

    # Action details
    action_type: str = Field(index=True)  # price_change, strategy_update, rule_creation, etc.
    action_description: str
    action_source: str  # manual, automated, api, system

    # State changes
    before_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    after_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    changed_fields: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Context and reasoning
    decision_reasoning: str | None = Field(default=None, sa_column=Text)
    market_conditions: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    business_context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Impact and outcomes
    immediate_impact: dict[str, float] | None = Field(default_factory=dict, sa_column=Column(JSON))
    expected_impact: dict[str, float] | None = Field(default_factory=dict, sa_column=Column(JSON))
    actual_impact: dict[str, float] | None = Field(default_factory=dict, sa_column=Column(JSON))

    # Compliance and approval
    compliance_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    approval_required: bool = Field(default=False)
    approved_by: str | None = None
    approved_at: datetime | None = None

    # Technical details
    api_endpoint: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    ip_address: str | None = None

    # Timestamps
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional metadata
    meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))


# View definitions for common queries
class PricingSummaryView(SQLModel):
    """View for pricing summary analytics"""

    __tablename__ = "pricing_summary_view"

    provider_id: str
    resource_type: ResourceType
    region: str
    current_price: float
    price_trend: PriceTrend
    price_volatility: float
    utilization_rate: float
    strategy_used: PricingStrategyType
    strategy_effectiveness: float
    last_updated: datetime
    total_revenue_7d: float
    market_share: float


class MarketHeatmapView(SQLModel):
    """View for market heatmap data"""

    __tablename__ = "market_heatmap_view"

    region: str
    resource_type: ResourceType
    demand_level: float
    supply_level: float
    average_price: float
    price_volatility: float
    utilization_rate: float
    market_sentiment: float
    competitor_count: int
    timestamp: datetime
