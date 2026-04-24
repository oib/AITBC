

"""
Dynamic Pricing API Router
Provides RESTful endpoints for dynamic pricing management
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from ..domain.pricing_strategies import StrategyLibrary
from ..schemas.pricing import (
    BulkPricingUpdateRequest,
    BulkPricingUpdateResponse,
    DynamicPriceResponse,
    MarketAnalysisResponse,
    PriceForecast,
    PriceHistoryResponse,
    PricingRecommendation,
    PricingStrategyRequest,
    PricingStrategyResponse,
)
from ..services.dynamic_pricing_engine import DynamicPricingEngine, PriceConstraints, PricingStrategy, ResourceType
from ..services.market_data_collector import MarketDataCollector

router = APIRouter(prefix="/v1/pricing", tags=["dynamic-pricing"])

# Global instances (in production, these would be dependency injected)
pricing_engine = None
market_collector = None


async def get_pricing_engine() -> DynamicPricingEngine:
    """Get pricing engine instance"""
    global pricing_engine
    if pricing_engine is None:
        pricing_engine = DynamicPricingEngine(
            {"min_price": 0.001, "max_price": 1000.0, "update_interval": 300, "forecast_horizon": 72}
        )
        await pricing_engine.initialize()
    return pricing_engine


async def get_market_collector() -> MarketDataCollector:
    """Get market data collector instance"""
    global market_collector
    if market_collector is None:
        market_collector = MarketDataCollector({"websocket_port": 8765})
        await market_collector.initialize()
    return market_collector


# ---------------------------------------------------------------------------
# Core Pricing Endpoints
# ---------------------------------------------------------------------------


@router.get("/dynamic/{resource_type}/{resource_id}", response_model=DynamicPriceResponse)
async def get_dynamic_price(
    resource_type: str,
    resource_id: str,
    strategy: str | None = Query(default=None),
    region: str = Query(default="global"),
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
) -> DynamicPriceResponse:
    """Get current dynamic price for a resource"""

    try:
        # Validate resource type
        try:
            resource_enum = ResourceType(resource_type.lower())
        except ValueError:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Invalid resource type: {resource_type}")

        # Get base price (in production, this would come from database)
        base_price = 0.05  # Default base price

        # Parse strategy if provided
        strategy_enum = None
        if strategy:
            try:
                strategy_enum = PricingStrategy(strategy.lower())
            except ValueError:
                raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Invalid strategy: {strategy}")

        # Calculate dynamic price
        result = await engine.calculate_dynamic_price(
            resource_id=resource_id, resource_type=resource_enum, base_price=base_price, strategy=strategy_enum, region=region
        )

        return DynamicPriceResponse(
            resource_id=result.resource_id,
            resource_type=result.resource_type.value,
            current_price=result.current_price,
            recommended_price=result.recommended_price,
            price_trend=result.price_trend.value,
            confidence_score=result.confidence_score,
            factors_exposed=result.factors_exposed,
            reasoning=result.reasoning,
            next_update=result.next_update,
            strategy_used=result.strategy_used.value,
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to calculate dynamic price: {str(e)}"
        )


@router.get("/forecast/{resource_type}/{resource_id}", response_model=PriceForecast)
async def get_price_forecast(
    resource_type: str,
    resource_id: str,
    hours: int = Query(default=24, ge=1, le=168),  # 1 hour to 1 week
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
) -> PriceForecast:
    """Get pricing forecast for next N hours"""

    try:
        # Validate resource type
        try:
            ResourceType(resource_type.lower())
        except ValueError:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Invalid resource type: {resource_type}")

        # Get forecast
        forecast_points = await engine.get_price_forecast(resource_id, hours)

        return PriceForecast(
            resource_id=resource_id,
            resource_type=resource_type,
            forecast_hours=hours,
            time_points=[
                {
                    "timestamp": point.timestamp.isoformat(),
                    "price": point.price,
                    "demand_level": point.demand_level,
                    "supply_level": point.supply_level,
                    "confidence": point.confidence,
                    "strategy_used": point.strategy_used,
                }
                for point in forecast_points
            ],
            accuracy_score=(
                sum(point.confidence for point in forecast_points) / len(forecast_points) if forecast_points else 0.0
            ),
            generated_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate price forecast: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Strategy Management Endpoints
# ---------------------------------------------------------------------------


@router.post("/strategy/{provider_id}", response_model=PricingStrategyResponse)
async def set_pricing_strategy(
    provider_id: str, request: PricingStrategyRequest, engine: DynamicPricingEngine = Depends(get_pricing_engine)
) -> PricingStrategyResponse:
    """Set pricing strategy for a provider"""

    try:
        # Validate strategy
        try:
            strategy_enum = PricingStrategy(request.strategy.lower())
        except ValueError:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Invalid strategy: {request.strategy}")

        # Parse constraints
        constraints = None
        if request.constraints:
            constraints = PriceConstraints(
                min_price=request.constraints.get("min_price"),
                max_price=request.constraints.get("max_price"),
                max_change_percent=request.constraints.get("max_change_percent", 0.5),
                min_change_interval=request.constraints.get("min_change_interval", 300),
                strategy_lock_period=request.constraints.get("strategy_lock_period", 3600),
            )

        # Set strategy
        success = await engine.set_provider_strategy(provider_id, strategy_enum, constraints)

        if not success:
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to set pricing strategy"
            )

        return PricingStrategyResponse(
            provider_id=provider_id,
            strategy=request.strategy,
            constraints=request.constraints,
            set_at=datetime.utcnow().isoformat(),
            status="active",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to set pricing strategy: {str(e)}"
        )


@router.get("/strategy/{provider_id}", response_model=PricingStrategyResponse)
async def get_pricing_strategy(
    provider_id: str, engine: DynamicPricingEngine = Depends(get_pricing_engine)
) -> PricingStrategyResponse:
    """Get current pricing strategy for a provider"""

    try:
        # Get strategy from engine
        if provider_id not in engine.provider_strategies:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail=f"No strategy found for provider {provider_id}"
            )

        strategy = engine.provider_strategies[provider_id]
        constraints = engine.price_constraints.get(provider_id)

        constraints_dict = None
        if constraints:
            constraints_dict = {
                "min_price": constraints.min_price,
                "max_price": constraints.max_price,
                "max_change_percent": constraints.max_change_percent,
                "min_change_interval": constraints.min_change_interval,
                "strategy_lock_period": constraints.strategy_lock_period,
            }

        return PricingStrategyResponse(
            provider_id=provider_id,
            strategy=strategy.value,
            constraints=constraints_dict,
            set_at=datetime.utcnow().isoformat(),
            status="active",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get pricing strategy: {str(e)}"
        )


@router.get("/strategies/available", response_model=list[dict[str, Any]])
async def get_available_strategies() -> list[dict[str, Any]]:
    """Get list of available pricing strategies"""

    try:
        strategies = []

        for strategy_type, config in StrategyLibrary.get_all_strategies().items():
            strategies.append(
                {
                    "strategy": strategy_type.value,
                    "name": config.name,
                    "description": config.description,
                    "risk_tolerance": config.risk_tolerance.value,
                    "priority": config.priority.value,
                    "parameters": {
                        "base_multiplier": config.parameters.base_multiplier,
                        "demand_sensitivity": config.parameters.demand_sensitivity,
                        "competition_sensitivity": config.parameters.competition_sensitivity,
                        "max_price_change_percent": config.parameters.max_price_change_percent,
                    },
                }
            )

        return strategies

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get available strategies: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Market Analysis Endpoints
# ---------------------------------------------------------------------------


@router.get("/market-analysis", response_model=MarketAnalysisResponse)
async def get_market_analysis(
    region: str = Query(default="global"),
    resource_type: str = Query(default="gpu"),
    collector: MarketDataCollector = Depends(get_market_collector),
) -> MarketAnalysisResponse:
    """Get comprehensive market pricing analysis"""

    try:
        # Validate resource type
        try:
            ResourceType(resource_type.lower())
        except ValueError:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Invalid resource type: {resource_type}")

        # Get aggregated market data
        market_data = await collector.get_aggregated_data(resource_type, region)

        if not market_data:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail=f"No market data available for {resource_type} in {region}"
            )

        # Get recent data for trend analysis
        await collector.get_recent_data("gpu_metrics", 60)
        recent_booking_data = await collector.get_recent_data("booking_data", 60)

        # Calculate trends
        demand_trend = "stable"
        supply_trend = "stable"
        price_trend = "stable"

        if len(recent_booking_data) > 1:
            recent_demand = [point.metadata.get("demand_level", 0.5) for point in recent_booking_data[-10:]]
            if recent_demand:
                avg_recent = sum(recent_demand[-5:]) / 5
                avg_older = sum(recent_demand[:5]) / 5
                change = (avg_recent - avg_older) / avg_older if avg_older > 0 else 0

                if change > 0.1:
                    demand_trend = "increasing"
                elif change < -0.1:
                    demand_trend = "decreasing"

        # Generate recommendations
        recommendations = []

        if market_data.demand_level > 0.8:
            recommendations.append("High demand detected - consider premium pricing")

        if market_data.supply_level < 0.3:
            recommendations.append("Low supply detected - prices may increase")

        if market_data.price_volatility > 0.2:
            recommendations.append("High price volatility - consider stable pricing strategy")

        if market_data.utilization_rate > 0.9:
            recommendations.append("High utilization - capacity constraints may affect pricing")

        return MarketAnalysisResponse(
            region=region,
            resource_type=resource_type,
            current_conditions={
                "demand_level": market_data.demand_level,
                "supply_level": market_data.supply_level,
                "average_price": market_data.average_price,
                "price_volatility": market_data.price_volatility,
                "utilization_rate": market_data.utilization_rate,
                "market_sentiment": market_data.market_sentiment,
            },
            trends={"demand_trend": demand_trend, "supply_trend": supply_trend, "price_trend": price_trend},
            competitor_analysis={
                "average_competitor_price": (
                    sum(market_data.competitor_prices) / len(market_data.competitor_prices)
                    if market_data.competitor_prices
                    else 0
                ),
                "price_range": {
                    "min": min(market_data.competitor_prices) if market_data.competitor_prices else 0,
                    "max": max(market_data.competitor_prices) if market_data.competitor_prices else 0,
                },
                "competitor_count": len(market_data.competitor_prices),
            },
            recommendations=recommendations,
            confidence_score=market_data.confidence_score,
            analysis_timestamp=market_data.timestamp.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get market analysis: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Recommendations Endpoints
# ---------------------------------------------------------------------------


@router.get("/recommendations/{provider_id}", response_model=list[PricingRecommendation])
async def get_pricing_recommendations(
    provider_id: str,
    resource_type: str = Query(default="gpu"),
    region: str = Query(default="global"),
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
    collector: MarketDataCollector = Depends(get_market_collector),
) -> list[PricingRecommendation]:
    """Get pricing optimization recommendations for a provider"""

    try:
        # Validate resource type
        try:
            ResourceType(resource_type.lower())
        except ValueError:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Invalid resource type: {resource_type}")

        recommendations = []

        # Get market data
        market_data = await collector.get_aggregated_data(resource_type, region)

        if not market_data:
            return []

        # Get provider's current strategy
        current_strategy = engine.provider_strategies.get(provider_id, PricingStrategy.MARKET_BALANCE)

        # Generate recommendations based on market conditions
        if market_data.demand_level > 0.8 and market_data.supply_level < 0.4:
            recommendations.append(
                PricingRecommendation(
                    type="strategy_change",
                    title="Switch to Profit Maximization",
                    description="High demand and low supply conditions favor profit maximization strategy",
                    impact="high",
                    confidence=0.85,
                    action="Set strategy to profit_maximization",
                    expected_outcome="+15-25% revenue increase",
                )
            )

        if market_data.price_volatility > 0.25:
            recommendations.append(
                PricingRecommendation(
                    type="risk_management",
                    title="Enable Price Stability Mode",
                    description="High volatility detected - enable stability constraints",
                    impact="medium",
                    confidence=0.9,
                    action="Set max_price_change_percent to 0.15",
                    expected_outcome="Reduced price volatility by 60%",
                )
            )

        if market_data.utilization_rate < 0.5:
            recommendations.append(
                PricingRecommendation(
                    type="competitive_response",
                    title="Aggressive Competitive Pricing",
                    description="Low utilization suggests need for competitive pricing",
                    impact="high",
                    confidence=0.75,
                    action="Set strategy to competitive_response",
                    expected_outcome="+10-20% utilization increase",
                )
            )

        # Strategy-specific recommendations
        if current_strategy == PricingStrategy.MARKET_BALANCE:
            recommendations.append(
                PricingRecommendation(
                    type="optimization",
                    title="Consider Dynamic Strategy",
                    description="Market conditions favor more dynamic pricing approach",
                    impact="medium",
                    confidence=0.7,
                    action="Evaluate demand_elasticity or competitive_response strategies",
                    expected_outcome="Improved market responsiveness",
                )
            )

        # Performance-based recommendations
        if provider_id in engine.pricing_history:
            history = engine.pricing_history[provider_id]
            if len(history) > 10:
                recent_prices = [point.price for point in history[-10:]]
                price_variance = sum((p - sum(recent_prices) / len(recent_prices)) ** 2 for p in recent_prices) / len(
                    recent_prices
                )

                if price_variance > (sum(recent_prices) / len(recent_prices) * 0.01):
                    recommendations.append(
                        PricingRecommendation(
                            type="stability",
                            title="Reduce Price Variance",
                            description="High price variance detected - consider stability improvements",
                            impact="medium",
                            confidence=0.8,
                            action="Enable confidence_threshold of 0.8",
                            expected_outcome="More stable pricing patterns",
                        )
                    )

        return recommendations

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get pricing recommendations: {str(e)}"
        )


# ---------------------------------------------------------------------------
# History and Analytics Endpoints
# ---------------------------------------------------------------------------


@router.get("/history/{resource_id}", response_model=PriceHistoryResponse)
async def get_price_history(
    resource_id: str,
    period: str = Query(default="7d", regex="^(1d|7d|30d|90d)$"),
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
) -> PriceHistoryResponse:
    """Get historical pricing data for a resource"""

    try:
        # Parse period
        period_days = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
        days = period_days.get(period, 7)

        # Get pricing history
        if resource_id not in engine.pricing_history:
            return PriceHistoryResponse(
                resource_id=resource_id,
                period=period,
                data_points=[],
                statistics={"average_price": 0, "min_price": 0, "max_price": 0, "price_volatility": 0, "total_changes": 0},
            )

        # Filter history by period
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        filtered_history = [point for point in engine.pricing_history[resource_id] if point.timestamp >= cutoff_time]

        # Calculate statistics
        if filtered_history:
            prices = [point.price for point in filtered_history]
            average_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)

            # Calculate volatility
            variance = sum((p - average_price) ** 2 for p in prices) / len(prices)
            price_volatility = (variance**0.5) / average_price if average_price > 0 else 0

            # Count price changes
            total_changes = 0
            for i in range(1, len(filtered_history)):
                if abs(filtered_history[i].price - filtered_history[i - 1].price) > 0.001:
                    total_changes += 1
        else:
            average_price = min_price = max_price = price_volatility = total_changes = 0

        return PriceHistoryResponse(
            resource_id=resource_id,
            period=period,
            data_points=[
                {
                    "timestamp": point.timestamp.isoformat(),
                    "price": point.price,
                    "demand_level": point.demand_level,
                    "supply_level": point.supply_level,
                    "confidence": point.confidence,
                    "strategy_used": point.strategy_used,
                }
                for point in filtered_history
            ],
            statistics={
                "average_price": average_price,
                "min_price": min_price,
                "max_price": max_price,
                "price_volatility": price_volatility,
                "total_changes": total_changes,
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get price history: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Bulk Operations Endpoints
# ---------------------------------------------------------------------------


@router.post("/bulk-update", response_model=BulkPricingUpdateResponse)
async def bulk_pricing_update(
    request: BulkPricingUpdateRequest, engine: DynamicPricingEngine = Depends(get_pricing_engine)
) -> BulkPricingUpdateResponse:
    """Bulk update pricing for multiple resources"""

    try:
        results = []
        success_count = 0
        error_count = 0

        for update in request.updates:
            try:
                # Validate strategy
                strategy_enum = PricingStrategy(update.strategy.lower())

                # Parse constraints
                constraints = None
                if update.constraints:
                    constraints = PriceConstraints(
                        min_price=update.constraints.get("min_price"),
                        max_price=update.constraints.get("max_price"),
                        max_change_percent=update.constraints.get("max_change_percent", 0.5),
                        min_change_interval=update.constraints.get("min_change_interval", 300),
                        strategy_lock_period=update.constraints.get("strategy_lock_period", 3600),
                    )

                # Set strategy
                success = await engine.set_provider_strategy(update.provider_id, strategy_enum, constraints)

                if success:
                    success_count += 1
                    results.append(
                        {"provider_id": update.provider_id, "status": "success", "message": "Strategy updated successfully"}
                    )
                else:
                    error_count += 1
                    results.append(
                        {"provider_id": update.provider_id, "status": "error", "message": "Failed to update strategy"}
                    )

            except Exception as e:
                error_count += 1
                results.append({"provider_id": update.provider_id, "status": "error", "message": str(e)})

        return BulkPricingUpdateResponse(
            total_updates=len(request.updates),
            success_count=success_count,
            error_count=error_count,
            results=results,
            processed_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process bulk update: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Health Check Endpoint
# ---------------------------------------------------------------------------


@router.get("/health")
async def pricing_health_check(
    engine: DynamicPricingEngine = Depends(get_pricing_engine), collector: MarketDataCollector = Depends(get_market_collector)
) -> dict[str, Any]:
    """Health check for pricing services"""

    try:
        # Check engine status
        engine_status = "healthy"
        engine_errors = []

        if not engine.pricing_history:
            engine_errors.append("No pricing history available")

        if not engine.provider_strategies:
            engine_errors.append("No provider strategies configured")

        if engine_errors:
            engine_status = "degraded"

        # Check collector status
        collector_status = "healthy"
        collector_errors = []

        if not collector.aggregated_data:
            collector_errors.append("No aggregated market data available")

        if len(collector.raw_data) < 10:
            collector_errors.append("Insufficient raw market data")

        if collector_errors:
            collector_status = "degraded"

        # Overall status
        overall_status = "healthy"
        if engine_status == "degraded" or collector_status == "degraded":
            overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "pricing_engine": {
                    "status": engine_status,
                    "errors": engine_errors,
                    "providers_configured": len(engine.provider_strategies),
                    "resources_tracked": len(engine.pricing_history),
                },
                "market_collector": {
                    "status": collector_status,
                    "errors": collector_errors,
                    "data_points_collected": len(collector.raw_data),
                    "aggregated_regions": len(collector.aggregated_data),
                },
            },
        }

    except Exception as e:
        logger.error(f"Dynamic pricing health check failed: {e}")
        return {"status": "unhealthy", "timestamp": datetime.utcnow().isoformat(), "error": "Health check failed"}
