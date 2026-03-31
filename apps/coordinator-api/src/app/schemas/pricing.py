"""
Pricing API Schemas
Pydantic models for dynamic pricing API requests and responses
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, validator


class PricingStrategy(StrEnum):
    """Pricing strategy enumeration"""

    AGGRESSIVE_GROWTH = "aggressive_growth"
    PROFIT_MAXIMIZATION = "profit_maximization"
    MARKET_BALANCE = "market_balance"
    COMPETITIVE_RESPONSE = "competitive_response"
    DEMAND_ELASTICITY = "demand_elasticity"
    PENETRATION_PRICING = "penetration_pricing"
    PREMIUM_PRICING = "premium_pricing"


class ResourceType(StrEnum):
    """Resource type enumeration"""

    GPU = "gpu"
    SERVICE = "service"
    STORAGE = "storage"


class PriceTrend(StrEnum):
    """Price trend enumeration"""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class DynamicPriceRequest(BaseModel):
    """Request for dynamic price calculation"""

    resource_id: str = Field(..., description="Unique resource identifier")
    resource_type: ResourceType = Field(..., description="Type of resource")
    base_price: float = Field(..., gt=0, description="Base price for calculation")
    strategy: PricingStrategy | None = Field(None, description="Pricing strategy to use")
    constraints: dict[str, Any] | None = Field(None, description="Pricing constraints")
    region: str = Field("global", description="Geographic region")


class PricingStrategyRequest(BaseModel):
    """Request to set pricing strategy"""

    strategy: PricingStrategy = Field(..., description="Pricing strategy")
    constraints: dict[str, Any] | None = Field(None, description="Strategy constraints")
    resource_types: list[ResourceType] | None = Field(None, description="Applicable resource types")
    regions: list[str] | None = Field(None, description="Applicable regions")

    @validator("constraints")
    def validate_constraints(cls, v):
        if v is not None:
            # Validate constraint fields
            if "min_price" in v and v["min_price"] is not None and v["min_price"] <= 0:
                raise ValueError("min_price must be greater than 0")
            if "max_price" in v and v["max_price"] is not None and v["max_price"] <= 0:
                raise ValueError("max_price must be greater than 0")
            if "min_price" in v and "max_price" in v:
                if v["min_price"] is not None and v["max_price"] is not None:
                    if v["min_price"] >= v["max_price"]:
                        raise ValueError("min_price must be less than max_price")
            if "max_change_percent" in v:
                if not (0 <= v["max_change_percent"] <= 1):
                    raise ValueError("max_change_percent must be between 0 and 1")
        return v


class BulkPricingUpdate(BaseModel):
    """Individual bulk pricing update"""

    provider_id: str = Field(..., description="Provider identifier")
    strategy: PricingStrategy = Field(..., description="Pricing strategy")
    constraints: dict[str, Any] | None = Field(None, description="Strategy constraints")
    resource_types: list[ResourceType] | None = Field(None, description="Applicable resource types")


class BulkPricingUpdateRequest(BaseModel):
    """Request for bulk pricing updates"""

    updates: list[BulkPricingUpdate] = Field(..., description="List of updates to apply")
    dry_run: bool = Field(False, description="Run in dry-run mode without applying changes")


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class DynamicPriceResponse(BaseModel):
    """Response for dynamic price calculation"""

    resource_id: str = Field(..., description="Resource identifier")
    resource_type: str = Field(..., description="Resource type")
    current_price: float = Field(..., description="Current base price")
    recommended_price: float = Field(..., description="Calculated dynamic price")
    price_trend: str = Field(..., description="Price trend indicator")
    confidence_score: float = Field(..., ge=0, le=1, description="Confidence in price calculation")
    factors_exposed: dict[str, float] = Field(..., description="Pricing factors breakdown")
    reasoning: list[str] = Field(..., description="Explanation of price calculation")
    next_update: datetime = Field(..., description="Next scheduled price update")
    strategy_used: str = Field(..., description="Strategy used for calculation")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PricePoint(BaseModel):
    """Single price point in forecast"""

    timestamp: str = Field(..., description="Timestamp of price point")
    price: float = Field(..., description="Forecasted price")
    demand_level: float = Field(..., ge=0, le=1, description="Expected demand level")
    supply_level: float = Field(..., ge=0, le=1, description="Expected supply level")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in forecast")
    strategy_used: str = Field(..., description="Strategy used for forecast")


class PriceForecast(BaseModel):
    """Price forecast response"""

    resource_id: str = Field(..., description="Resource identifier")
    resource_type: str = Field(..., description="Resource type")
    forecast_hours: int = Field(..., description="Number of hours forecasted")
    time_points: list[PricePoint] = Field(..., description="Forecast time points")
    accuracy_score: float = Field(..., ge=0, le=1, description="Overall forecast accuracy")
    generated_at: str = Field(..., description="When forecast was generated")


class PricingStrategyResponse(BaseModel):
    """Response for pricing strategy operations"""

    provider_id: str = Field(..., description="Provider identifier")
    strategy: str = Field(..., description="Strategy name")
    constraints: dict[str, Any] | None = Field(None, description="Strategy constraints")
    set_at: str = Field(..., description="When strategy was set")
    status: str = Field(..., description="Strategy status")


class MarketConditions(BaseModel):
    """Current market conditions"""

    demand_level: float = Field(..., ge=0, le=1, description="Current demand level")
    supply_level: float = Field(..., ge=0, le=1, description="Current supply level")
    average_price: float = Field(..., ge=0, description="Average market price")
    price_volatility: float = Field(..., ge=0, description="Price volatility index")
    utilization_rate: float = Field(..., ge=0, le=1, description="Resource utilization rate")
    market_sentiment: float = Field(..., ge=-1, le=1, description="Market sentiment score")


class MarketTrends(BaseModel):
    """Market trend information"""

    demand_trend: str = Field(..., description="Demand trend direction")
    supply_trend: str = Field(..., description="Supply trend direction")
    price_trend: str = Field(..., description="Price trend direction")


class CompetitorAnalysis(BaseModel):
    """Competitor pricing analysis"""

    average_competitor_price: float = Field(..., ge=0, description="Average competitor price")
    price_range: dict[str, float] = Field(..., description="Price range (min/max)")
    competitor_count: int = Field(..., ge=0, description="Number of competitors tracked")


class MarketAnalysisResponse(BaseModel):
    """Market analysis response"""

    region: str = Field(..., description="Analysis region")
    resource_type: str = Field(..., description="Resource type analyzed")
    current_conditions: MarketConditions = Field(..., description="Current market conditions")
    trends: MarketTrends = Field(..., description="Market trends")
    competitor_analysis: CompetitorAnalysis = Field(..., description="Competitor analysis")
    recommendations: list[str] = Field(..., description="Market-based recommendations")
    confidence_score: float = Field(..., ge=0, le=1, description="Analysis confidence")
    analysis_timestamp: str = Field(..., description="When analysis was performed")


class PricingRecommendation(BaseModel):
    """Pricing optimization recommendation"""

    type: str = Field(..., description="Recommendation type")
    title: str = Field(..., description="Recommendation title")
    description: str = Field(..., description="Detailed recommendation description")
    impact: str = Field(..., description="Expected impact level")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in recommendation")
    action: str = Field(..., description="Recommended action")
    expected_outcome: str = Field(..., description="Expected outcome")


class PriceHistoryPoint(BaseModel):
    """Single point in price history"""

    timestamp: str = Field(..., description="Timestamp of price point")
    price: float = Field(..., description="Price at timestamp")
    demand_level: float = Field(..., ge=0, le=1, description="Demand level at timestamp")
    supply_level: float = Field(..., ge=0, le=1, description="Supply level at timestamp")
    confidence: float = Field(..., ge=0, le=1, description="Confidence at timestamp")
    strategy_used: str = Field(..., description="Strategy used at timestamp")


class PriceStatistics(BaseModel):
    """Price statistics"""

    average_price: float = Field(..., ge=0, description="Average price")
    min_price: float = Field(..., ge=0, description="Minimum price")
    max_price: float = Field(..., ge=0, description="Maximum price")
    price_volatility: float = Field(..., ge=0, description="Price volatility")
    total_changes: int = Field(..., ge=0, description="Total number of price changes")


class PriceHistoryResponse(BaseModel):
    """Price history response"""

    resource_id: str = Field(..., description="Resource identifier")
    period: str = Field(..., description="Time period covered")
    data_points: list[PriceHistoryPoint] = Field(..., description="Historical price points")
    statistics: PriceStatistics = Field(..., description="Price statistics for period")


class BulkUpdateResult(BaseModel):
    """Result of individual bulk update"""

    provider_id: str = Field(..., description="Provider identifier")
    status: str = Field(..., description="Update status")
    message: str = Field(..., description="Status message")


class BulkPricingUpdateResponse(BaseModel):
    """Response for bulk pricing updates"""

    total_updates: int = Field(..., description="Total number of updates requested")
    success_count: int = Field(..., description="Number of successful updates")
    error_count: int = Field(..., description="Number of failed updates")
    results: list[BulkUpdateResult] = Field(..., description="Individual update results")
    processed_at: str = Field(..., description="When updates were processed")


# ---------------------------------------------------------------------------
# Internal Data Schemas
# ---------------------------------------------------------------------------


class PricingFactors(BaseModel):
    """Pricing calculation factors"""

    base_price: float = Field(..., description="Base price")
    demand_multiplier: float = Field(..., description="Demand-based multiplier")
    supply_multiplier: float = Field(..., description="Supply-based multiplier")
    time_multiplier: float = Field(..., description="Time-based multiplier")
    performance_multiplier: float = Field(..., description="Performance-based multiplier")
    competition_multiplier: float = Field(..., description="Competition-based multiplier")
    sentiment_multiplier: float = Field(..., description="Sentiment-based multiplier")
    regional_multiplier: float = Field(..., description="Regional multiplier")
    confidence_score: float = Field(..., ge=0, le=1, description="Overall confidence")
    risk_adjustment: float = Field(..., description="Risk adjustment factor")
    demand_level: float = Field(..., ge=0, le=1, description="Current demand level")
    supply_level: float = Field(..., ge=0, le=1, description="Current supply level")
    market_volatility: float = Field(..., ge=0, description="Market volatility")
    provider_reputation: float = Field(..., description="Provider reputation factor")
    utilization_rate: float = Field(..., ge=0, le=1, description="Utilization rate")
    historical_performance: float = Field(..., description="Historical performance factor")


class PriceConstraints(BaseModel):
    """Pricing calculation constraints"""

    min_price: float | None = Field(None, ge=0, description="Minimum allowed price")
    max_price: float | None = Field(None, ge=0, description="Maximum allowed price")
    max_change_percent: float = Field(0.5, ge=0, le=1, description="Maximum percent change per update")
    min_change_interval: int = Field(300, ge=60, description="Minimum seconds between changes")
    strategy_lock_period: int = Field(3600, ge=300, description="Strategy lock period in seconds")


class StrategyParameters(BaseModel):
    """Strategy configuration parameters"""

    base_multiplier: float = Field(1.0, ge=0.1, le=3.0, description="Base price multiplier")
    min_price_margin: float = Field(0.1, ge=0, le=1, description="Minimum price margin")
    max_price_margin: float = Field(2.0, ge=0, le=5.0, description="Maximum price margin")
    demand_sensitivity: float = Field(0.5, ge=0, le=1, description="Demand sensitivity factor")
    supply_sensitivity: float = Field(0.3, ge=0, le=1, description="Supply sensitivity factor")
    competition_sensitivity: float = Field(0.4, ge=0, le=1, description="Competition sensitivity factor")
    peak_hour_multiplier: float = Field(1.2, ge=0.5, le=2.0, description="Peak hour multiplier")
    off_peak_multiplier: float = Field(0.8, ge=0.5, le=1.5, description="Off-peak multiplier")
    weekend_multiplier: float = Field(1.1, ge=0.5, le=2.0, description="Weekend multiplier")
    performance_bonus_rate: float = Field(0.1, ge=0, le=0.5, description="Performance bonus rate")
    performance_penalty_rate: float = Field(0.05, ge=0, le=0.3, description="Performance penalty rate")
    max_price_change_percent: float = Field(0.3, ge=0, le=1, description="Maximum price change percent")
    volatility_threshold: float = Field(0.2, ge=0, le=1, description="Volatility threshold")
    confidence_threshold: float = Field(0.7, ge=0, le=1, description="Confidence threshold")
    growth_target_rate: float = Field(0.15, ge=0, le=1, description="Growth target rate")
    profit_target_margin: float = Field(0.25, ge=0, le=1, description="Profit target margin")
    market_share_target: float = Field(0.1, ge=0, le=1, description="Market share target")
    regional_adjustments: dict[str, float] = Field(default_factory=dict, description="Regional adjustments")
    custom_parameters: dict[str, Any] = Field(default_factory=dict, description="Custom parameters")


class MarketDataPoint(BaseModel):
    """Market data point"""

    source: str = Field(..., description="Data source")
    resource_id: str = Field(..., description="Resource identifier")
    resource_type: str = Field(..., description="Resource type")
    region: str = Field(..., description="Geographic region")
    timestamp: datetime = Field(..., description="Data timestamp")
    value: float = Field(..., description="Data value")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class AggregatedMarketData(BaseModel):
    """Aggregated market data"""

    resource_type: str = Field(..., description="Resource type")
    region: str = Field(..., description="Geographic region")
    timestamp: datetime = Field(..., description="Aggregation timestamp")
    demand_level: float = Field(..., ge=0, le=1, description="Aggregated demand level")
    supply_level: float = Field(..., ge=0, le=1, description="Aggregated supply level")
    average_price: float = Field(..., ge=0, description="Average price")
    price_volatility: float = Field(..., ge=0, description="Price volatility")
    utilization_rate: float = Field(..., ge=0, le=1, description="Utilization rate")
    competitor_prices: list[float] = Field(default_factory=list, description="Competitor prices")
    market_sentiment: float = Field(..., ge=-1, le=1, description="Market sentiment")
    data_sources: list[str] = Field(default_factory=list, description="Data sources used")
    confidence_score: float = Field(..., ge=0, le=1, description="Aggregation confidence")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ---------------------------------------------------------------------------
# Error Response Schemas
# ---------------------------------------------------------------------------


class PricingError(BaseModel):
    """Pricing error response"""

    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ValidationError(BaseModel):
    """Validation error response"""

    field: str = Field(..., description="Field with validation error")
    message: str = Field(..., description="Validation error message")
    value: Any = Field(..., description="Invalid value provided")


# ---------------------------------------------------------------------------
# Configuration Schemas
# ---------------------------------------------------------------------------


class PricingEngineConfig(BaseModel):
    """Pricing engine configuration"""

    min_price: float = Field(0.001, gt=0, description="Minimum allowed price")
    max_price: float = Field(1000.0, gt=0, description="Maximum allowed price")
    update_interval: int = Field(300, ge=60, description="Update interval in seconds")
    forecast_horizon: int = Field(72, ge=1, le=168, description="Forecast horizon in hours")
    max_volatility_threshold: float = Field(0.3, ge=0, le=1, description="Max volatility threshold")
    circuit_breaker_threshold: float = Field(0.5, ge=0, le=1, description="Circuit breaker threshold")
    enable_ml_optimization: bool = Field(True, description="Enable ML optimization")
    cache_ttl: int = Field(300, ge=60, description="Cache TTL in seconds")


class MarketCollectorConfig(BaseModel):
    """Market data collector configuration"""

    websocket_port: int = Field(8765, ge=1024, le=65535, description="WebSocket port")
    collection_intervals: dict[str, int] = Field(
        default={
            "gpu_metrics": 60,
            "booking_data": 30,
            "regional_demand": 300,
            "competitor_prices": 600,
            "performance_data": 120,
            "market_sentiment": 180,
        },
        description="Collection intervals in seconds",
    )
    max_data_age_hours: int = Field(48, ge=1, le=168, description="Maximum data age in hours")
    max_raw_data_points: int = Field(10000, ge=1000, description="Maximum raw data points")
    enable_websocket_broadcast: bool = Field(True, description="Enable WebSocket broadcasting")


# ---------------------------------------------------------------------------
# Analytics Schemas
# ---------------------------------------------------------------------------


class PricingAnalytics(BaseModel):
    """Pricing analytics data"""

    provider_id: str = Field(..., description="Provider identifier")
    period_start: datetime = Field(..., description="Analysis period start")
    period_end: datetime = Field(..., description="Analysis period end")
    total_revenue: float = Field(..., ge=0, description="Total revenue")
    average_price: float = Field(..., ge=0, description="Average price")
    price_volatility: float = Field(..., ge=0, description="Price volatility")
    utilization_rate: float = Field(..., ge=0, le=1, description="Average utilization rate")
    strategy_effectiveness: float = Field(..., ge=0, le=1, description="Strategy effectiveness score")
    market_share: float = Field(..., ge=0, le=1, description="Market share")
    customer_satisfaction: float = Field(..., ge=0, le=1, description="Customer satisfaction score")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StrategyPerformance(BaseModel):
    """Strategy performance metrics"""

    strategy: str = Field(..., description="Strategy name")
    total_providers: int = Field(..., ge=0, description="Number of providers using strategy")
    average_revenue_impact: float = Field(..., description="Average revenue impact")
    average_market_share_change: float = Field(..., description="Average market share change")
    customer_satisfaction_impact: float = Field(..., description="Customer satisfaction impact")
    price_stability_score: float = Field(..., ge=0, le=1, description="Price stability score")
    adoption_rate: float = Field(..., ge=0, le=1, description="Strategy adoption rate")
    effectiveness_score: float = Field(..., ge=0, le=1, description="Overall effectiveness score")
