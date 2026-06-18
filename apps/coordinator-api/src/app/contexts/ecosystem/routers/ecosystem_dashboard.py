"""
Ecosystem Metrics Dashboard API
REST API for developer ecosystem metrics and analytics
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ....auth import AuthDep
from ....services.ecosystem_service import EcosystemService
from ....storage import get_session

logger = get_logger(__name__)

router = APIRouter()


class DeveloperEarningsResponse(BaseModel):
    period: str
    total_earnings: float
    average_earnings: float
    top_earners: list[dict[str, Any]]
    earnings_growth: float
    active_developers: int


class AgentUtilizationResponse(BaseModel):
    period: str
    total_agents: int
    active_agents: int
    utilization_rate: float
    top_utilized_agents: list[dict[str, Any]]
    average_performance: float
    performance_distribution: dict[str, int]


class TreasuryAllocationResponse(BaseModel):
    period: str
    treasury_balance: float
    total_inflow: float
    total_outflow: float
    dao_revenue: float
    allocation_breakdown: dict[str, float]
    burn_rate: float


class StakingMetricsResponse(BaseModel):
    period: str
    total_staked: float
    total_stakers: int
    average_apy: float
    staking_rewards_total: float
    top_staking_pools: list[dict[str, Any]]
    tier_distribution: dict[str, int]


class BountyAnalyticsResponse(BaseModel):
    period: str
    active_bounties: int
    completion_rate: float
    average_reward: float
    total_volume: float
    category_distribution: dict[str, int]
    difficulty_distribution: dict[str, int]


class EcosystemOverviewResponse(BaseModel):
    timestamp: datetime
    period_type: str
    developer_earnings: DeveloperEarningsResponse
    agent_utilization: AgentUtilizationResponse
    treasury_allocation: TreasuryAllocationResponse
    staking_metrics: StakingMetricsResponse
    bounty_analytics: BountyAnalyticsResponse
    health_score: float
    growth_indicators: dict[str, float]


class MetricsFilterRequest(BaseModel):
    period_type: str = Field(default="daily", pattern="^(hourly|daily|weekly|monthly)$")
    start_date: datetime | None = None
    end_date: datetime | None = None
    compare_period: str | None = None


def get_ecosystem_service(session: Annotated[Session, Depends(get_session)]) -> EcosystemService:
    return EcosystemService(session)


@router.get("/ecosystem/developer-earnings", response_model=DeveloperEarningsResponse)
@rate_limit(rate=200, per=60)
async def get_developer_earnings(
    request: Request,
    period: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
    user: AuthDep,
) -> DeveloperEarningsResponse:
    """Get developer earnings metrics"""
    try:
        earnings_data = await ecosystem_service.get_developer_earnings(period=period)
        return DeveloperEarningsResponse(period=period, **earnings_data)
    except Exception as e:
        logger.error("Failed to get developer earnings: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/agent-utilization", response_model=AgentUtilizationResponse)
@rate_limit(rate=200, per=60)
async def get_agent_utilization(
    request: Request,
    period: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> AgentUtilizationResponse:
    """Get agent utilization metrics"""
    try:
        utilization_data = await ecosystem_service.get_agent_utilization(period=period)
        return AgentUtilizationResponse(period=period, **utilization_data)
    except Exception as e:
        logger.error("Failed to get agent utilization: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/treasury-allocation", response_model=TreasuryAllocationResponse)
@rate_limit(rate=200, per=60)
async def get_treasury_allocation(
    request: Request,
    period: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> TreasuryAllocationResponse:
    """Get DAO treasury allocation metrics"""
    try:
        treasury_data = await ecosystem_service.get_treasury_allocation(period=period)
        return TreasuryAllocationResponse(period=period, **treasury_data)
    except Exception as e:
        logger.error("Failed to get treasury allocation: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/staking-metrics", response_model=StakingMetricsResponse)
@rate_limit(rate=200, per=60)
async def get_staking_metrics(
    request: Request,
    period: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> StakingMetricsResponse:
    """Get staking system metrics"""
    try:
        staking_data = await ecosystem_service.get_staking_metrics(period=period)
        return StakingMetricsResponse(period=period, **staking_data)
    except Exception as e:
        logger.error("Failed to get staking metrics: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/bounty-analytics", response_model=BountyAnalyticsResponse)
@rate_limit(rate=200, per=60)
async def get_bounty_analytics(
    request: Request,
    period: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> BountyAnalyticsResponse:
    """Get bounty system analytics"""
    try:
        bounty_data = await ecosystem_service.get_bounty_analytics(period=period)
        return BountyAnalyticsResponse(period=period, **bounty_data)
    except Exception as e:
        logger.error("Failed to get bounty analytics: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/overview", response_model=EcosystemOverviewResponse)
@rate_limit(rate=100, per=60)
async def get_ecosystem_overview(
    request: Request,
    period_type: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> EcosystemOverviewResponse:
    """Get comprehensive ecosystem overview"""
    try:
        overview_data = await ecosystem_service.get_ecosystem_overview(period_type=period_type)
        return EcosystemOverviewResponse(
            timestamp=overview_data["timestamp"],
            period_type=period_type,
            developer_earnings=DeveloperEarningsResponse(**overview_data["developer_earnings"]),
            agent_utilization=AgentUtilizationResponse(**overview_data["agent_utilization"]),
            treasury_allocation=TreasuryAllocationResponse(**overview_data["treasury_allocation"]),
            staking_metrics=StakingMetricsResponse(**overview_data["staking_metrics"]),
            bounty_analytics=BountyAnalyticsResponse(**overview_data["bounty_analytics"]),
            health_score=overview_data["health_score"],
            growth_indicators=overview_data["growth_indicators"],
        )
    except Exception as e:
        logger.error("Failed to get ecosystem overview: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/metrics")
@rate_limit(rate=200, per=60)
async def get_ecosystem_metrics(
    request: Request,
    period_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get time-series ecosystem metrics"""
    try:
        metrics = await ecosystem_service.get_time_series_metrics(
            period_type=period_type, start_date=start_date, end_date=end_date, limit=limit
        )
        return {"metrics": metrics, "period_type": period_type, "count": len(metrics)}
    except Exception as e:
        logger.error("Failed to get ecosystem metrics: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/health-score")
@rate_limit(rate=200, per=60)
async def get_ecosystem_health_score(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get overall ecosystem health score"""
    try:
        health_score = await ecosystem_service.calculate_health_score()  # type: ignore[call-arg]
        return {
            "health_score": health_score["score"],
            "components": health_score["components"],
            "recommendations": health_score["recommendations"],
            "last_updated": health_score["last_updated"],
        }  # type: ignore[index]
    except Exception as e:
        logger.error("Failed to get health score: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/growth-indicators")
@rate_limit(rate=200, per=60)
async def get_growth_indicators(
    request: Request,
    period: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get ecosystem growth indicators"""
    try:
        growth_data = await ecosystem_service.get_growth_indicators(period=period)  # type: ignore[attr-defined]
        return {
            "period": period,
            "indicators": growth_data,
            "trend": growth_data.get("trend", "stable"),
            "growth_rate": growth_data.get("growth_rate", 0.0),
        }
    except Exception as e:
        logger.error("Failed to get growth indicators: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/top-performers")
@rate_limit(rate=200, per=60)
async def get_top_performers(
    request: Request,
    category: str | None,
    period: str | None,
    limit: int | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get top performers in different categories"""
    try:
        performers = await ecosystem_service.get_top_performers(category=category, period=period, limit=limit)
        return {"category": category, "period": period, "performers": performers, "count": len(performers)}
    except Exception as e:
        logger.error("Failed to get top performers: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/predictions")
@rate_limit(rate=200, per=60)
async def get_ecosystem_predictions(
    request: Request,
    metric: str | None,
    horizon: int | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get ecosystem predictions based on historical data"""
    try:
        predictions = await ecosystem_service.get_predictions(metric=metric, horizon=horizon)
        return {
            "metric": metric,
            "horizon_days": horizon,
            "predictions": predictions,
            "confidence": predictions.get("confidence", 0.0),
            "model_used": predictions.get("model", "linear_regression"),
        }
    except Exception as e:
        logger.error("Failed to get predictions: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/alerts")
@rate_limit(rate=200, per=60)
async def get_ecosystem_alerts(
    request: Request,
    severity: str | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get ecosystem alerts and anomalies"""
    try:
        alerts = await ecosystem_service.get_alerts(severity=severity)
        return {"alerts": alerts, "severity": severity, "count": len(alerts), "last_updated": datetime.now(UTC)}
    except Exception as e:
        logger.error("Failed to get alerts: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/comparison")
@rate_limit(rate=200, per=60)
async def get_ecosystem_comparison(
    request: Request,
    current_period: str | None,
    compare_period: str | None,
    custom_start_date: datetime | None,
    custom_end_date: datetime | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Compare ecosystem metrics between periods"""
    try:
        comparison = await ecosystem_service.get_period_comparison(
            current_period=current_period,
            compare_period=compare_period,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date,
        )
        return {
            "current_period": current_period,
            "compare_period": compare_period,
            "comparison": comparison,
            "summary": comparison.get("summary", {}),
        }
    except Exception as e:
        logger.error("Failed to get comparison: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/export")
@rate_limit(rate=50, per=60)
async def export_ecosystem_data(
    request: Request,
    format: str | None,
    period_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Export ecosystem data in various formats"""
    try:
        export_data = await ecosystem_service.export_data(
            format=format, period_type=period_type, start_date=start_date, end_date=end_date
        )
        return {
            "format": format,
            "period_type": period_type,
            "data_url": export_data["url"],
            "file_size": export_data.get("file_size", 0),
            "expires_at": export_data.get("expires_at"),
            "record_count": export_data.get("record_count", 0),
        }
    except Exception as e:
        logger.error("Failed to export data: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/real-time")
@rate_limit(rate=100, per=60)
async def get_real_time_metrics(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get real-time ecosystem metrics"""
    try:
        real_time_data = await ecosystem_service.get_real_time_metrics()
        return {"timestamp": datetime.now(UTC), "metrics": real_time_data, "update_frequency": "60s"}
    except Exception as e:
        logger.error("Failed to get real-time metrics: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/ecosystem/kpi-dashboard")
@rate_limit(rate=200, per=60)
async def get_kpi_dashboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    ecosystem_service: Annotated[EcosystemService, Depends(get_ecosystem_service)],
) -> dict[str, Any]:
    """Get KPI dashboard with key performance indicators"""
    try:
        kpi_data = await ecosystem_service.get_kpi_dashboard()
        return {"kpis": kpi_data, "last_updated": datetime.now(UTC), "refresh_interval": 300}
    except Exception as e:
        logger.error("Failed to get KPI dashboard: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
