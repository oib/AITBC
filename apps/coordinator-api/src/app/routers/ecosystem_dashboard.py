from typing import Annotated
"""
Ecosystem Metrics Dashboard API
REST API for developer ecosystem metrics and analytics
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..logging import get_logger
from ..domain.bounty import EcosystemMetrics, BountyStats, AgentMetrics
from ..services.ecosystem_service import EcosystemService
from ..auth import get_current_user

logger = get_logger(__name__)
router = APIRouter()

# Pydantic models for request/response
class DeveloperEarningsResponse(BaseModel):
    period: str
    total_earnings: float
    average_earnings: float
    top_earners: List[Dict[str, Any]]
    earnings_growth: float
    active_developers: int

class AgentUtilizationResponse(BaseModel):
    period: str
    total_agents: int
    active_agents: int
    utilization_rate: float
    top_utilized_agents: List[Dict[str, Any]]
    average_performance: float
    performance_distribution: Dict[str, int]

class TreasuryAllocationResponse(BaseModel):
    period: str
    treasury_balance: float
    total_inflow: float
    total_outflow: float
    dao_revenue: float
    allocation_breakdown: Dict[str, float]
    burn_rate: float

class StakingMetricsResponse(BaseModel):
    period: str
    total_staked: float
    total_stakers: int
    average_apy: float
    staking_rewards_total: float
    top_staking_pools: List[Dict[str, Any]]
    tier_distribution: Dict[str, int]

class BountyAnalyticsResponse(BaseModel):
    period: str
    active_bounties: int
    completion_rate: float
    average_reward: float
    total_volume: float
    category_distribution: Dict[str, int]
    difficulty_distribution: Dict[str, int]

class EcosystemOverviewResponse(BaseModel):
    timestamp: datetime
    period_type: str
    developer_earnings: DeveloperEarningsResponse
    agent_utilization: AgentUtilizationResponse
    treasury_allocation: TreasuryAllocationResponse
    staking_metrics: StakingMetricsResponse
    bounty_analytics: BountyAnalyticsResponse
    health_score: float
    growth_indicators: Dict[str, float]

class MetricsFilterRequest(BaseModel):
    period_type: str = Field(default="daily", regex="^(hourly|daily|weekly|monthly)$")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    compare_period: Optional[str] = None

# Dependency injection
def get_ecosystem_service(session: Annotated[Session, Depends(get_session)]) -> EcosystemService:
    return EcosystemService(session)

# API endpoints
@router.get("/ecosystem/developer-earnings", response_model=DeveloperEarningsResponse)
async def get_developer_earnings(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service),
    current_user: dict = Depends(get_current_user)
):
    """Get developer earnings metrics"""
    try:
        earnings_data = await ecosystem_service.get_developer_earnings(period=period)
        
        return DeveloperEarningsResponse(
            period=period,
            **earnings_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get developer earnings: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/agent-utilization", response_model=AgentUtilizationResponse)
async def get_agent_utilization(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get agent utilization metrics"""
    try:
        utilization_data = await ecosystem_service.get_agent_utilization(period=period)
        
        return AgentUtilizationResponse(
            period=period,
            **utilization_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get agent utilization: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/treasury-allocation", response_model=TreasuryAllocationResponse)
async def get_treasury_allocation(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get DAO treasury allocation metrics"""
    try:
        treasury_data = await ecosystem_service.get_treasury_allocation(period=period)
        
        return TreasuryAllocationResponse(
            period=period,
            **treasury_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get treasury allocation: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/staking-metrics", response_model=StakingMetricsResponse)
async def get_staking_metrics(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get staking system metrics"""
    try:
        staking_data = await ecosystem_service.get_staking_metrics(period=period)
        
        return StakingMetricsResponse(
            period=period,
            **staking_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get staking metrics: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/bounty-analytics", response_model=BountyAnalyticsResponse)
async def get_bounty_analytics(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get bounty system analytics"""
    try:
        bounty_data = await ecosystem_service.get_bounty_analytics(period=period)
        
        return BountyAnalyticsResponse(
            period=period,
            **bounty_data
        )
        
    except Exception as e:
        logger.error(f"Failed to get bounty analytics: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/overview", response_model=EcosystemOverviewResponse)
async def get_ecosystem_overview(
    period_type: str = Field(default="daily", regex="^(hourly|daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
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
            growth_indicators=overview_data["growth_indicators"]
        )
        
    except Exception as e:
        logger.error(f"Failed to get ecosystem overview: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/metrics")
async def get_ecosystem_metrics(
    period_type: str = Field(default="daily", regex="^(hourly|daily|weekly|monthly)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Field(default=100, ge=1, le=1000),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get time-series ecosystem metrics"""
    try:
        metrics = await ecosystem_service.get_time_series_metrics(
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return {
            "metrics": metrics,
            "period_type": period_type,
            "count": len(metrics)
        }
        
    except Exception as e:
        logger.error(f"Failed to get ecosystem metrics: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/health-score")
async def get_ecosystem_health_score(
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get overall ecosystem health score"""
    try:
        health_score = await ecosystem_service.calculate_health_score()
        
        return {
            "health_score": health_score["score"],
            "components": health_score["components"],
            "recommendations": health_score["recommendations"],
            "last_updated": health_score["last_updated"]
        }
        
    except Exception as e:
        logger.error(f"Failed to get health score: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/growth-indicators")
async def get_growth_indicators(
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get ecosystem growth indicators"""
    try:
        growth_data = await ecosystem_service.get_growth_indicators(period=period)
        
        return {
            "period": period,
            "indicators": growth_data,
            "trend": growth_data.get("trend", "stable"),
            "growth_rate": growth_data.get("growth_rate", 0.0)
        }
        
    except Exception as e:
        logger.error(f"Failed to get growth indicators: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/top-performers")
async def get_top_performers(
    category: str = Field(default="all", regex="^(developers|agents|stakers|all)$"),
    period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    limit: int = Field(default=50, ge=1, le=100),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get top performers in different categories"""
    try:
        performers = await ecosystem_service.get_top_performers(
            category=category,
            period=period,
            limit=limit
        )
        
        return {
            "category": category,
            "period": period,
            "performers": performers,
            "count": len(performers)
        }
        
    except Exception as e:
        logger.error(f"Failed to get top performers: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/predictions")
async def get_ecosystem_predictions(
    metric: str = Field(default="all", regex="^(earnings|staking|bounties|agents|all)$"),
    horizon: int = Field(default=30, ge=1, le=365),  # days
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get ecosystem predictions based on historical data"""
    try:
        predictions = await ecosystem_service.get_predictions(
            metric=metric,
            horizon=horizon
        )
        
        return {
            "metric": metric,
            "horizon_days": horizon,
            "predictions": predictions,
            "confidence": predictions.get("confidence", 0.0),
            "model_used": predictions.get("model", "linear_regression")
        }
        
    except Exception as e:
        logger.error(f"Failed to get predictions: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/alerts")
async def get_ecosystem_alerts(
    severity: str = Field(default="all", regex="^(low|medium|high|critical|all)$"),
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get ecosystem alerts and anomalies"""
    try:
        alerts = await ecosystem_service.get_alerts(severity=severity)
        
        return {
            "alerts": alerts,
            "severity": severity,
            "count": len(alerts),
            "last_updated": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/comparison")
async def get_ecosystem_comparison(
    current_period: str = Field(default="monthly", regex="^(daily|weekly|monthly)$"),
    compare_period: str = Field(default="previous", regex="^(previous|same_last_year|custom)$"),
    custom_start_date: Optional[datetime] = None,
    custom_end_date: Optional[datetime] = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Compare ecosystem metrics between periods"""
    try:
        comparison = await ecosystem_service.get_period_comparison(
            current_period=current_period,
            compare_period=compare_period,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date
        )
        
        return {
            "current_period": current_period,
            "compare_period": compare_period,
            "comparison": comparison,
            "summary": comparison.get("summary", {})
        }
        
    except Exception as e:
        logger.error(f"Failed to get comparison: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/export")
async def export_ecosystem_data(
    format: str = Field(default="json", regex="^(json|csv|xlsx)$"),
    period_type: str = Field(default="daily", regex="^(hourly|daily|weekly|monthly)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Export ecosystem data in various formats"""
    try:
        export_data = await ecosystem_service.export_data(
            format=format,
            period_type=period_type,
            start_date=start_date,
            end_date=end_date
        )
        
        return {
            "format": format,
            "period_type": period_type,
            "data_url": export_data["url"],
            "file_size": export_data.get("file_size", 0),
            "expires_at": export_data.get("expires_at"),
            "record_count": export_data.get("record_count", 0)
        }
        
    except Exception as e:
        logger.error(f"Failed to export data: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/real-time")
async def get_real_time_metrics(
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get real-time ecosystem metrics"""
    try:
        real_time_data = await ecosystem_service.get_real_time_metrics()
        
        return {
            "timestamp": datetime.utcnow(),
            "metrics": real_time_data,
            "update_frequency": "60s"  # Update frequency in seconds
        }
        
    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ecosystem/kpi-dashboard")
async def get_kpi_dashboard(
    session: Annotated[Session, Depends(get_session)] = Depends(),
    ecosystem_service: EcosystemService = Depends(get_ecosystem_service)
):
    """Get KPI dashboard with key performance indicators"""
    try:
        kpi_data = await ecosystem_service.get_kpi_dashboard()
        
        return {
            "kpis": kpi_data,
            "last_updated": datetime.utcnow(),
            "refresh_interval": 300  # 5 minutes
        }
        
    except Exception as e:
        logger.error(f"Failed to get KPI dashboard: {e}")
        raise HTTPException(status_code=400, detail=str(e))
