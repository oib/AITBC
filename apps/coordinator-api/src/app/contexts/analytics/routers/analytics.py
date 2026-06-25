"""
Marketplace Analytics API Endpoints
REST API for analytics, insights, reporting, and dashboards
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlmodel import select

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..domain.analytics import (
    AnalyticsPeriod,
    AnalyticsReport,
    DashboardConfig,
    MarketInsight,
    MarketMetric,
    ReportType,
)
from ...agent_coordination.services.agent_marketplace import AgentServiceMarketplace
from ....storage import get_session

logger = get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


class MetricResponse(BaseModel):
    """Response model for market metric"""

    metric_name: str
    metric_type: str
    period_type: str
    value: float
    previous_value: float | None
    change_percentage: float | None
    unit: str
    category: str
    recorded_at: str
    period_start: str
    period_end: str
    breakdown: dict[str, Any]
    comparisons: dict[str, Any]


class InsightResponse(BaseModel):
    """Response model for market insight"""

    id: str
    insight_type: str
    title: str
    description: str
    confidence_score: float
    impact_level: str
    related_metrics: list[str]
    time_horizon: str
    recommendations: list[str]
    suggested_actions: list[dict[str, Any]]
    created_at: str
    expires_at: str | None
    insight_data: dict[str, Any]


class DashboardResponse(BaseModel):
    """Response model for dashboard configuration"""

    dashboard_id: str
    name: str
    description: str
    dashboard_type: str
    layout: dict[str, Any]
    widgets: list[dict[str, Any]]
    filters: list[dict[str, Any]]
    refresh_interval: int
    auto_refresh: bool
    owner_id: str
    status: str
    created_at: str
    updated_at: str


class ReportRequest(BaseModel):
    """Request model for generating analytics report"""

    report_type: ReportType
    period_type: AnalyticsPeriod
    start_date: str
    end_date: str
    filters: dict[str, Any] = Field(default_factory=dict)
    include_charts: bool = Field(default=True)
    format: str = Field(default="json")


class MarketOverviewResponse(BaseModel):
    """Response model for market overview"""

    timestamp: str
    period: str
    metrics: dict[str, Any]
    insights: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    summary: dict[str, Any]


class AnalyticsSummaryResponse(BaseModel):
    """Response model for analytics summary"""

    period_type: str
    start_time: str
    end_time: str
    metrics_collected: int
    insights_generated: int
    market_data: dict[str, Any]


@router.post("/data-collection", response_model=AnalyticsSummaryResponse)
@rate_limit(rate=20, per=60)
async def collect_market_data(
    request: Request,
    period_type: AnalyticsPeriod | None,
    session: Annotated[Session, Depends(get_session)],
) -> AnalyticsSummaryResponse:
    """Collect market data for analytics"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        result = await analytics_service.collect_market_data(period_type)  # type: ignore[attr-defined]
        return AnalyticsSummaryResponse(**result)
    except Exception as e:
        logger.error("Error collecting market data: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/insights", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_market_insights(
    request: Request,
    time_period: str | None,
    insight_type: str | None,
    impact_level: str | None,
    limit: int | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get market insights and analysis"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        result = await analytics_service.generate_insights(time_period)  # type: ignore[attr-defined]
        if insight_type or impact_level:
            filtered_insights = {}
            for type_name, insights in result["insight_groups"].items():
                filtered = insights
                if insight_type:
                    filtered = [i for i in filtered if i["type"] == insight_type]
                if impact_level:
                    filtered = [i for i in filtered if i["impact"] == impact_level]
                if filtered:
                    filtered_insights[type_name] = filtered[:limit]
            result["insight_groups"] = filtered_insights
            result["total_insights"] = sum(len(insights) for insights in filtered_insights.values())
        return result  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Error getting market insights: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/metrics", response_model=list[MetricResponse])
@rate_limit(rate=200, per=60)
async def get_market_metrics(
    request: Request,
    period_type: AnalyticsPeriod | None,
    metric_name: str | None,
    category: str | None,
    geographic_region: str | None,
    limit: int | None,
    session: Annotated[Session, Depends(get_session)],
) -> list[MetricResponse]:
    """Get market metrics with filters"""
    try:
        query = select(MarketMetric).where(MarketMetric.period_type == period_type)
        if metric_name:
            query = query.where(MarketMetric.metric_name == metric_name)
        if category:
            query = query.where(MarketMetric.category == category)
        if geographic_region:
            query = query.where(MarketMetric.geographic_region == geographic_region)
        metrics = session.execute(query.order_by(desc(MarketMetric.recorded_at)).limit(limit)).all()  # type: ignore[arg-type]
        return [
            MetricResponse(
                metric_name=metric.metric_name,
                metric_type=metric.metric_type.value,
                period_type=metric.period_type.value,
                value=metric.value,
                previous_value=metric.previous_value,
                change_percentage=metric.change_percentage,
                unit=metric.unit,
                category=metric.category,
                recorded_at=metric.recorded_at.isoformat(),
                period_start=metric.period_start.isoformat(),
                period_end=metric.period_end.isoformat(),
                breakdown=metric.breakdown,
                comparisons=metric.comparisons,
            )
            for metric in metrics
        ]
    except Exception as e:
        logger.error("Error getting market metrics: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/overview", response_model=MarketOverviewResponse)
@rate_limit(rate=200, per=60)
async def get_market_overview(request: Request, session: Annotated[Session, Depends(get_session)]) -> MarketOverviewResponse:
    """Get comprehensive market overview"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        overview = await analytics_service.get_market_overview()  # type: ignore[attr-defined]
        return MarketOverviewResponse(**overview)
    except Exception as e:
        logger.error("Error getting market overview: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/dashboards", response_model=DashboardResponse)
@rate_limit(rate=20, per=60)
async def create_dashboard(
    request: Request,
    name: str,
    dashboard_type: str,
    layout: dict[str, Any],
    widgets: list[dict[str, Any]],
    filters: list[dict[str, Any]] | None,
    session: Annotated[Session, Depends(get_session)],
) -> DashboardResponse:
    """Create analytics dashboard"""
    try:
        dashboard = DashboardConfig(
            dashboard_id=str(uuid4()),
            name=name,
            description="",
            dashboard_type=dashboard_type,
            layout=layout,
            widgets=widgets,
            filters=filters or [],
            refresh_interval=300,
            auto_refresh=True,
            owner_id="system",
            status="active",
        )
        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)
        return DashboardResponse(
            dashboard_id=dashboard.dashboard_id,
            name=dashboard.name,
            description=dashboard.description,
            dashboard_type=dashboard.dashboard_type,
            layout=dashboard.layout,
            widgets=dashboard.widgets,
            filters=dashboard.filters,
            refresh_interval=dashboard.refresh_interval,
            auto_refresh=dashboard.auto_refresh,
            owner_id=dashboard.owner_id,
            status=dashboard.status.value,
            created_at=dashboard.created_at.isoformat(),
            updated_at=dashboard.updated_at.isoformat(),
        )
    except Exception as e:
        logger.error("Error creating dashboard: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/dashboards/{dashboard_id}", response_model=DashboardResponse)
@rate_limit(rate=200, per=60)
async def get_dashboard(
    request: Request,
    dashboard_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> DashboardResponse:
    """Get dashboard configuration"""
    try:
        dashboard = session.get(DashboardConfig, dashboard_id)
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return DashboardResponse(
            dashboard_id=dashboard.dashboard_id,
            name=dashboard.name,
            description=dashboard.description,
            dashboard_type=dashboard.dashboard_type,
            layout=dashboard.layout,
            widgets=dashboard.widgets,
            filters=dashboard.filters,
            refresh_interval=dashboard.refresh_interval,
            auto_refresh=dashboard.auto_refresh,
            owner_id=dashboard.owner_id,
            status=dashboard.status.value,
            created_at=dashboard.created_at.isoformat(),
            updated_at=dashboard.updated_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting dashboard: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/reports", response_model=AnalyticsReport)
@rate_limit(rate=20, per=60)
async def generate_report(
    request: Request,
    report_request: ReportRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AnalyticsReport:
    """Generate analytics report"""
    try:
        report = AnalyticsReport(
            report_id=str(uuid4()),
            report_type=report_request.report_type,
            period_type=report_request.period_type,
            start_date=datetime.fromisoformat(report_request.start_date),
            end_date=datetime.fromisoformat(report_request.end_date),
            filters=report_request.filters,
            include_charts=report_request.include_charts,
            format=report_request.format,
            status="pending",
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report
    except Exception as e:
        logger.error("Error generating report: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/reports/{report_id}", response_model=AnalyticsReport)
@rate_limit(rate=200, per=60)
async def get_report(
    request: Request,
    report_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> AnalyticsReport:
    """Get analytics report"""
    try:
        report = session.get(AnalyticsReport, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting report: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/insights/generate", response_model=MarketInsight)
@rate_limit(rate=20, per=60)
async def generate_insight(
    request: Request,
    insight_type: str,
    title: str,
    description: str,
    confidence_score: float | None,
    impact_level: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> MarketInsight:
    """Generate market insight"""
    try:
        insight = MarketInsight(
            id=str(uuid4()),
            insight_type=insight_type,
            title=title,
            description=description,
            confidence_score=confidence_score,
            impact_level=impact_level,
            related_metrics=[],
            time_horizon="short_term",
            recommendations=[],
            suggested_actions=[],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        session.add(insight)
        session.commit()
        session.refresh(insight)
        return insight
    except Exception as e:
        logger.error("Error generating insight: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/insights/{insight_id}", response_model=MarketInsight)
@rate_limit(rate=200, per=60)
async def get_insight(
    request: Request,
    insight_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> MarketInsight:
    """Get specific market insight"""
    try:
        insight = session.get(MarketInsight, insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")
        return insight
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting insight: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/market/trends", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_market_trends(
    request: Request,
    time_period: str | None,
    metric_categories: list[str] | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get market trends analysis"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        trends = await analytics_service.analyze_market_trends(time_period=time_period, metric_categories=metric_categories)  # type: ignore[attr-defined]
        return trends
    except Exception as e:
        logger.error("Error getting market trends: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/market/segments", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_market_segments(
    request: Request,
    segment_by: str | None,
    min_market_share: float | None,
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Get market segment analysis"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        segments = await analytics_service.analyze_market_segments(segment_by=segment_by, min_market_share=min_market_share)  # type: ignore[attr-defined]
        return segments
    except Exception as e:
        logger.error("Error getting market segments: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/competitors/analysis", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_competitor_analysis(
    request: Request,
    competitor_ids: list[str] | None,
    analysis_depth: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get competitive analysis"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        analysis = await analytics_service.analyze_competitors(competitor_ids=competitor_ids, analysis_depth=analysis_depth)  # type: ignore[attr-defined]
        return analysis
    except Exception as e:
        logger.error("Error getting competitor analysis: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/forecasts/{metric_name}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_metric_forecast(
    request: Request,
    metric_name: str,
    forecast_periods: int | None,
    confidence_interval: float | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get metric forecast"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        forecast = await analytics_service.forecast_metric(
            metric_name=metric_name,
            forecast_periods=forecast_periods,
            confidence_interval=confidence_interval,
        )  # type: ignore[attr-defined]
        return forecast
    except Exception as e:
        logger.error("Error getting metric forecast: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/alerts/active", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_active_alerts(
    request: Request,
    severity: str | None,
    category: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Get active market alerts"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        alerts = await analytics_service.get_active_alerts(severity=severity, category=category)  # type: ignore[attr-defined]
        return alerts
    except Exception as e:
        logger.error("Error getting active alerts: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/alerts/acknowledge/{alert_id}")
@rate_limit(rate=50, per=60)
async def acknowledge_alert(
    request: Request,
    alert_id: str,
    acknowledged_by: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Acknowledge market alert"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        result = await analytics_service.acknowledge_alert(alert_id=alert_id, acknowledged_by=acknowledged_by)  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error("Error acknowledging alert: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/performance/benchmarks", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_performance_benchmarks(
    request: Request,
    benchmark_type: str | None,
    time_period: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get performance benchmarks"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        benchmarks = await analytics_service.get_performance_benchmarks(benchmark_type=benchmark_type, time_period=time_period)  # type: ignore[attr-defined]
        return benchmarks
    except Exception as e:
        logger.error("Error getting performance benchmarks: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/custom/queries", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_custom_queries(
    request: Request,
    query_type: str | None,
    created_by: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    """Get saved custom queries"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        queries = await analytics_service.get_custom_queries(query_type=query_type, created_by=created_by)  # type: ignore[attr-defined]
        return queries
    except Exception as e:
        logger.error("Error getting custom queries: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/custom/queries")
@rate_limit(rate=20, per=60)
async def create_custom_query(
    request: Request,
    query_name: str,
    query_definition: dict[str, Any],
    query_type: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Create custom analytics query"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        query = await analytics_service.create_custom_query(
            query_name=query_name, query_definition=query_definition, query_type=query_type
        )  # type: ignore[attr-defined]
        return query
    except Exception as e:
        logger.error("Error creating custom query: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/custom/queries/{query_id}/execute")
@rate_limit(rate=50, per=60)
async def execute_custom_query(
    request: Request,
    query_id: str,
    parameters: dict[str, Any] | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Execute custom analytics query"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        result = await analytics_service.execute_custom_query(query_id=query_id, parameters=parameters or {})  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error("Error executing custom query: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/export/data", response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def export_analytics_data(
    request: Request,
    export_format: str | None,
    data_types: list[str] | None,
    date_range: str | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Export analytics data"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        export_result = await analytics_service.export_analytics_data(
            export_format=export_format, data_types=data_types, date_range=date_range
        )  # type: ignore[attr-defined]
        return export_result
    except Exception as e:
        logger.error("Error exporting analytics data: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/realtime/metrics", response_model=dict[str, Any])
@rate_limit(rate=1000, per=60)
async def get_realtime_metrics(
    request: Request,
    metric_names: list[str] | None,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get real-time market metrics"""
    analytics_service = AgentServiceMarketplace(session)  # type: ignore[arg-type]
    try:
        metrics = await analytics_service.get_realtime_metrics(metric_names=metric_names)  # type: ignore[attr-defined]
        return metrics
    except Exception as e:
        logger.error("Error getting realtime metrics: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/health", response_model=dict[str, Any])
@rate_limit(rate=100, per=60)
async def analytics_health_check(request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Health check for analytics service"""
    try:
        return {
            "status": "healthy",
            "service": "analytics",
            "timestamp": datetime.now(UTC).isoformat(),
            "database_connected": True,
            "metrics_available": True,
        }
    except Exception as e:
        logger.error("Analytics health check failed: %s", str(e))
        return {
            "status": "unhealthy",
            "service": "analytics",
            "timestamp": datetime.now(UTC).isoformat(),
            "error": str(e),
        }
