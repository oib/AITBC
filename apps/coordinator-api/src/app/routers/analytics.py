from typing import Annotated

from sqlalchemy.orm import Session

"""
Marketplace Analytics API Endpoints
REST API for analytics, insights, reporting, and dashboards
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from aitbc import get_logger

logger = get_logger(__name__)

from ..domain.analytics import (
    AnalyticsPeriod,
    AnalyticsReport,
    DashboardConfig,
    InsightType,
    MarketInsight,
    MarketMetric,
    MetricType,
    ReportType,
)
from ..services.analytics_service import MarketplaceAnalytics
from ..storage import get_session

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


# Pydantic models for API requests/responses
class MetricResponse(BaseModel):
    """Response model for market metric"""
    metric_name: str
    metric_type: str
    period_type: str
    value: float
    previous_value: Optional[float]
    change_percentage: Optional[float]
    unit: str
    category: str
    recorded_at: str
    period_start: str
    period_end: str
    breakdown: Dict[str, Any]
    comparisons: Dict[str, Any]


class InsightResponse(BaseModel):
    """Response model for market insight"""
    id: str
    insight_type: str
    title: str
    description: str
    confidence_score: float
    impact_level: str
    related_metrics: List[str]
    time_horizon: str
    recommendations: List[str]
    suggested_actions: List[Dict[str, Any]]
    created_at: str
    expires_at: Optional[str]
    insight_data: Dict[str, Any]


class DashboardResponse(BaseModel):
    """Response model for dashboard configuration"""
    dashboard_id: str
    name: str
    description: str
    dashboard_type: str
    layout: Dict[str, Any]
    widgets: List[Dict[str, Any]]
    filters: List[Dict[str, Any]]
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
    filters: Dict[str, Any] = Field(default_factory=dict)
    include_charts: bool = Field(default=True)
    format: str = Field(default="json")


class MarketOverviewResponse(BaseModel):
    """Response model for market overview"""
    timestamp: str
    period: str
    metrics: Dict[str, Any]
    insights: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    summary: Dict[str, Any]


class AnalyticsSummaryResponse(BaseModel):
    """Response model for analytics summary"""
    period_type: str
    start_time: str
    end_time: str
    metrics_collected: int
    insights_generated: int
    market_data: Dict[str, Any]


# API Endpoints

@router.post("/data-collection", response_model=AnalyticsSummaryResponse)
async def collect_market_data(
    period_type: AnalyticsPeriod = Query(default=AnalyticsPeriod.DAILY, description="Collection period"),
    session: Session = Depends(get_session),
) -> AnalyticsSummaryResponse:
    """Collect market data for analytics"""
    
    analytics_service = MarketplaceAnalytics(session)
    
    try:
        result = await analytics_service.collect_market_data(period_type)
        
        return AnalyticsSummaryResponse(**result)
        
    except Exception as e:
        logger.error(f"Error collecting market data: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/insights", response_model=Dict[str, Any])
async def get_market_insights(
    time_period: str = Query(default="daily", description="Time period: daily, weekly, monthly"),
    insight_type: Optional[str] = Query(default=None, description="Filter by insight type"),
    impact_level: Optional[str] = Query(default=None, description="Filter by impact level"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get market insights and analysis"""
    
    analytics_service = MarketplaceAnalytics(session)
    
    try:
        result = await analytics_service.generate_insights(time_period)
        
        # Apply filters if provided
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
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting market insights: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics", response_model=List[MetricResponse])
async def get_market_metrics(
    period_type: AnalyticsPeriod = Query(default=AnalyticsPeriod.DAILY, description="Period type"),
    metric_name: Optional[str] = Query(default=None, description="Filter by metric name"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    geographic_region: Optional[str] = Query(default=None, description="Filter by region"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session)
) -> List[MetricResponse]:
    """Get market metrics with filters"""
    
    try:
        query = select(MarketMetric).where(MarketMetric.period_type == period_type)
        
        if metric_name:
            query = query.where(MarketMetric.metric_name == metric_name)
        if category:
            query = query.where(MarketMetric.category == category)
        if geographic_region:
            query = query.where(MarketMetric.geographic_region == geographic_region)
        
        metrics = session.execute(
            query.order_by(MarketMetric.recorded_at.desc()).limit(limit)
        ).all()
        
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
                comparisons=metric.comparisons
            )
            for metric in metrics
        ]
        
    except Exception as e:
        logger.error(f"Error getting market metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/overview", response_model=MarketOverviewResponse)
async def get_market_overview(
    session: Session = Depends(get_session)
) -> MarketOverviewResponse:
    """Get comprehensive market overview"""
    
    analytics_service = MarketplaceAnalytics(session)
    
    try:
        overview = await analytics_service.get_market_overview()
        
        return MarketOverviewResponse(**overview)
        
    except Exception as e:
        logger.error(f"Error getting market overview: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/dashboards", response_model=DashboardResponse)
async def create_dashboard(
    owner_id: str,
    dashboard_type: str = Query(default="default", description="Dashboard type: default, executive"),
    name: Optional[str] = Query(default=None, description="Custom dashboard name"),
    session: Session = Depends(get_session)
) -> DashboardResponse:
    """Create analytics dashboard"""
    
    analytics_service = MarketplaceAnalytics(session)
    
    try:
        result = await analytics_service.create_dashboard(owner_id, dashboard_type)
        
        # Get the created dashboard details
        dashboard = session.execute(
            select(DashboardConfig).where(DashboardConfig.dashboard_id == result["dashboard_id"])
        ).first()
        
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found after creation")
        
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
            status=dashboard.status,
            created_at=dashboard.created_at.isoformat(),
            updated_at=dashboard.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error creating dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: str,
    session: Session = Depends(get_session)
) -> DashboardResponse:
    """Get dashboard configuration"""
    
    try:
        dashboard = session.execute(
            select(DashboardConfig).where(DashboardConfig.dashboard_id == dashboard_id)
        ).first()
        
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
            status=dashboard.status,
            created_at=dashboard.created_at.isoformat(),
            updated_at=dashboard.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard {dashboard_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboards")
async def list_dashboards(
    owner_id: Optional[str] = Query(default=None, description="Filter by owner ID"),
    dashboard_type: Optional[str] = Query(default=None, description="Filter by dashboard type"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session)
) -> List[DashboardResponse]:
    """List analytics dashboards with filters"""
    
    try:
        query = select(DashboardConfig)
        
        if owner_id:
            query = query.where(DashboardConfig.owner_id == owner_id)
        if dashboard_type:
            query = query.where(DashboardConfig.dashboard_type == dashboard_type)
        if status:
            query = query.where(DashboardConfig.status == status)
        
        dashboards = session.execute(
            query.order_by(DashboardConfig.created_at.desc()).limit(limit)
        ).all()
        
        return [
            DashboardResponse(
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
                status=dashboard.status,
                created_at=dashboard.created_at.isoformat(),
                updated_at=dashboard.updated_at.isoformat()
            )
            for dashboard in dashboards
        ]
        
    except Exception as e:
        logger.error(f"Error listing dashboards: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reports", response_model=Dict[str, Any])
async def generate_report(
    report_request: ReportRequest,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Generate analytics report"""
    
    try:
        # Parse dates
        start_date = datetime.fromisoformat(report_request.start_date)
        end_date = datetime.fromisoformat(report_request.end_date)
        
        # Create report record
        report = AnalyticsReport(
            report_id=f"report_{uuid4().hex[:8]}",
            report_type=report_request.report_type,
            title=f"{report_request.report_type.value.title()} Report",
            description=f"Analytics report for {report_request.period_type.value} period",
            period_type=report_request.period_type,
            start_date=start_date,
            end_date=end_date,
            filters=report_request.filters,
            generated_by="api",
            status="generated"
        )
        
        session.add(report)
        session.commit()
        session.refresh(report)
        
        # Generate report content based on type
        if report_request.report_type == ReportType.MARKET_OVERVIEW:
            content = await self.generate_market_overview_report(
                session, report_request.period_type, start_date, end_date, report_request.filters
            )
        elif report_request.report_type == ReportType.AGENT_PERFORMANCE:
            content = await self.generate_agent_performance_report(
                session, report_request.period_type, start_date, end_date, report_request.filters
            )
        elif report_request.report_type == ReportType.ECONOMIC_ANALYSIS:
            content = await self.generate_economic_analysis_report(
                session, report_request.period_type, start_date, end_date, report_request.filters
            )
        else:
            content = {"error": "Report type not implemented yet"}
        
        # Update report with content
        report.summary = content.get("summary", "")
        report.key_findings = content.get("key_findings", [])
        report.recommendations = content.get("recommendations", [])
        report.data_sections = content.get("data_sections", [])
        report.charts = content.get("charts", []) if report_request.include_charts else []
        report.tables = content.get("tables", [])
        
        session.commit()
        
        return {
            "report_id": report.report_id,
            "report_type": report.report_type.value,
            "title": report.title,
            "period": f"{report_request.period_type.value} from {report_request.start_date} to {report_request.end_date}",
            "summary": report.summary,
            "key_findings": report.key_findings,
            "recommendations": report.recommendations,
            "generated_at": report.generated_at.isoformat(),
            "format": report_request.format
        }
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    format: str = Query(default="json", description="Response format: json, csv, pdf"),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get generated analytics report"""
    
    try:
        report = session.execute(
            select(AnalyticsReport).where(AnalyticsReport.report_id == report_id)
        ).first()
        
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        response_data = {
            "report_id": report.report_id,
            "report_type": report.report_type.value,
            "title": report.title,
            "description": report.description,
            "period_type": report.period_type.value,
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "summary": report.summary,
            "key_findings": report.key_findings,
            "recommendations": report.recommendations,
            "data_sections": report.data_sections,
            "charts": report.charts,
            "tables": report.tables,
            "generated_at": report.generated_at.isoformat(),
            "status": report.status
        }
        
        # Format response based on requested format
        if format == "json":
            return response_data
        elif format == "csv":
            # Convert to CSV format (simplified)
            return {"csv_data": self.convert_to_csv(response_data)}
        elif format == "pdf":
            # Convert to PDF format (simplified)
            return {"pdf_url": f"/api/v1/analytics/reports/{report_id}/pdf"}
        else:
            return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report {report_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts")
async def get_analytics_alerts(
    severity: Optional[str] = Query(default=None, description="Filter by severity level"),
    status: Optional[str] = Query(default="active", description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get analytics alerts"""
    
    try:
        from ..domain.analytics import AnalyticsAlert
        
        query = select(AnalyticsAlert)
        
        if severity:
            query = query.where(AnalyticsAlert.severity == severity)
        if status:
            query = query.where(AnalyticsAlert.status == status)
        
        alerts = session.execute(
            query.order_by(AnalyticsAlert.created_at.desc()).limit(limit)
        ).all()
        
        return [
            {
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "alert_type": alert.alert_type,
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity,
                "confidence": alert.confidence,
                "trigger_value": alert.trigger_value,
                "threshold_value": alert.threshold_value,
                "affected_metrics": alert.affected_metrics,
                "status": alert.status,
                "created_at": alert.created_at.isoformat(),
                "expires_at": alert.expires_at.isoformat() if alert.expires_at else None
            }
            for alert in alerts
        ]
        
    except Exception as e:
        logger.error(f"Error getting analytics alerts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/kpi")
async def get_key_performance_indicators(
    period_type: AnalyticsPeriod = Query(default=AnalyticsPeriod.DAILY, description="Period type"),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get key performance indicators"""
    
    try:
        # Get latest metrics for KPIs
        end_time = datetime.now(timezone.utc)
        
        if period_type == AnalyticsPeriod.DAILY:
            start_time = end_time - timedelta(days=1)
        elif period_type == AnalyticsPeriod.WEEKLY:
            start_time = end_time - timedelta(weeks=1)
        elif period_type == AnalyticsPeriod.MONTHLY:
            start_time = end_time - timedelta(days=30)
        else:
            start_time = end_time - timedelta(hours=1)
        
        metrics = session.execute(
            select(MarketMetric).where(
                and_(
                    MarketMetric.period_type == period_type,
                    MarketMetric.period_start >= start_time,
                    MarketMetric.period_end <= end_time
                )
            ).order_by(MarketMetric.recorded_at.desc())
        ).all()
        
        # Calculate KPIs
        kpis = {}
        
        for metric in metrics:
            if metric.metric_name in ["transaction_volume", "active_agents", "average_price", "success_rate"]:
                kpis[metric.metric_name] = {
                    "value": metric.value,
                    "unit": metric.unit,
                    "change_percentage": metric.change_percentage,
                    "trend": "up" if metric.change_percentage and metric.change_percentage > 0 else "down",
                    "status": self.get_kpi_status(metric.metric_name, metric.value, metric.change_percentage)
                }
        
        return {
            "period_type": period_type.value,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "kpis": kpis,
            "overall_health": self.calculate_overall_health(kpis)
        }
        
    except Exception as e:
        logger.error(f"Error getting KPIs: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Helper methods
async def generate_market_overview_report(
    session: Session,
    period_type: AnalyticsPeriod,
    start_date: datetime,
    end_date: datetime,
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate market overview report content"""
    
    # Get metrics for the period
    metrics = session.execute(
        select(MarketMetric).where(
            and_(
                MarketMetric.period_type == period_type,
                MarketMetric.period_start >= start_date,
                MarketMetric.period_end <= end_date
            )
        ).order_by(MarketMetric.recorded_at.desc())
    ).all()
    
    # Get insights for the period
    insights = session.execute(
        select(MarketInsight).where(
            and_(
                MarketInsight.created_at >= start_date,
                MarketInsight.created_at <= end_date
            )
        ).order_by(MarketInsight.created_at.desc())
    ).all()
    
    return {
        "summary": f"Market overview for {period_type.value} period from {start_date.date()} to {end_date.date()}",
        "key_findings": [
            f"Total transaction volume: {next((m.value for m in metrics if m.metric_name == 'transaction_volume'), 0):.2f} AITBC",
            f"Active agents: {next((int(m.value) for m in metrics if m.metric_name == 'active_agents'), 0)}",
            f"Average success rate: {next((m.value for m in metrics if m.metric_name == 'success_rate'), 0):.1f}%",
            f"Total insights generated: {len(insights)}"
        ],
        "recommendations": [
            "Monitor transaction volume trends for growth opportunities",
            "Focus on improving agent success rates",
            "Analyze geographic distribution for market expansion"
        ],
        "data_sections": [
            {
                "title": "Transaction Metrics",
                "data": {
                    metric.metric_name: metric.value
                    for metric in metrics
                    if metric.category == "financial"
                }
            },
            {
                "title": "Agent Metrics",
                "data": {
                    metric.metric_name: metric.value
                    for metric in metrics
                    if metric.category == "agents"
                }
            }
        ],
        "charts": [
            {
                "type": "line",
                "title": "Transaction Volume Trend",
                "data": [m.value for m in metrics if m.metric_name == "transaction_volume"]
            },
            {
                "type": "pie",
                "title": "Agent Distribution by Tier",
                "data": next((m.breakdown.get("by_tier", {}) for m in metrics if m.metric_name == "active_agents"), {})
            }
        ]
    }


async def generate_agent_performance_report(
    session: Session,
    period_type: AnalyticsPeriod,
    start_date: datetime,
    end_date: datetime,
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate agent performance report content"""
    
    # Mock implementation - would query actual agent performance data
    return {
        "summary": f"Agent performance report for {period_type.value} period",
        "key_findings": [
            "Top performing agents show 20% higher success rates",
            "Agent retention rate improved by 5%",
            "Average agent earnings increased by 10%"
        ],
        "recommendations": [
            "Provide additional training for lower-performing agents",
            "Implement recognition programs for top performers",
            "Optimize agent matching algorithms"
        ],
        "data_sections": [
            {
                "title": "Performance Metrics",
                "data": {
                    "top_performers": 25,
                    "average_success_rate": 87.5,
                    "retention_rate": 92.0
                }
            }
        ]
    }


async def generate_economic_analysis_report(
    session: Session,
    period_type: AnalyticsPeriod,
    start_date: datetime,
    end_date: datetime,
    filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate economic analysis report content"""
    
    # Mock implementation - would query actual economic data
    return {
        "summary": f"Economic analysis for {period_type.value} period",
        "key_findings": [
            "Market showed 15% growth in transaction volume",
            "Price stability maintained across all regions",
            "Supply/demand balance improved by 10%"
        ],
        "recommendations": [
            "Continue current pricing strategies",
            "Focus on market expansion in high-growth regions",
            "Monitor supply/demand ratios for optimization"
        ],
        "data_sections": [
            {
                "title": "Economic Indicators",
                "data": {
                    "market_growth": 15.0,
                    "price_stability": 95.0,
                    "supply_demand_balance": 1.1
                }
            }
        ]
    }


def get_kpi_status(metric_name: str, value: float, change_percentage: Optional[float]) -> str:
    """Get KPI status based on value and change"""
    
    if metric_name == "success_rate":
        if value >= 90:
            return "excellent"
        elif value >= 80:
            return "good"
        elif value >= 70:
            return "fair"
        else:
            return "poor"
    elif metric_name == "transaction_volume":
        if change_percentage and change_percentage > 10:
            return "excellent"
        elif change_percentage and change_percentage > 0:
            return "good"
        elif change_percentage and change_percentage < -10:
            return "poor"
        else:
            return "fair"
    else:
        return "good"


def calculate_overall_health(kpis: Dict[str, Any]) -> str:
    """Calculate overall market health"""
    
    if not kpis:
        return "unknown"
    
    # Count KPIs by status
    status_counts = {}
    for kpi_data in kpis.values():
        status = kpi_data.get("status", "fair")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    total_kpis = len(kpis)
    
    # Determine overall health
    if status_counts.get("excellent", 0) >= total_kpis * 0.6:
        return "excellent"
    elif status_counts.get("excellent", 0) + status_counts.get("good", 0) >= total_kpis * 0.7:
        return "good"
    elif status_counts.get("poor", 0) >= total_kpis * 0.3:
        return "poor"
    else:
        return "fair"


def convert_to_csv(data: Dict[str, Any]) -> str:
    """Convert report data to CSV format (simplified)"""
    
    csv_lines = []
    
    # Add header
    csv_lines.append("Metric,Value,Unit,Change,Trend,Status")
    
    # Add KPI data if available
    if "kpis" in data:
        for metric_name, kpi_data in data["kpis"].items():
            csv_lines.append(
                f"{metric_name},{kpi_data.get('value', '')},{kpi_data.get('unit', '')},"
                f"{kpi_data.get('change_percentage', '')}%,{kpi_data.get('trend', '')},"
                f"{kpi_data.get('status', '')}"
            )
    
    return "\n".join(csv_lines)
