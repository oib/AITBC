"""
Marketplace Analytics Service
Implements comprehensive analytics, insights, and reporting for the marketplace
"""

from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from aitbc import get_logger

logger = get_logger(__name__)

from sqlmodel import Session, and_, select

from ..domain.analytics import (
    AnalyticsAlert,
    AnalyticsPeriod,
    DashboardConfig,
    InsightType,
    MarketInsight,
    MarketMetric,
    MetricType,
)


class DataCollector:
    """Comprehensive data collection system"""

    def __init__(self):
        self.collection_intervals = {
            AnalyticsPeriod.REALTIME: 60,  # 1 minute
            AnalyticsPeriod.HOURLY: 3600,  # 1 hour
            AnalyticsPeriod.DAILY: 86400,  # 1 day
            AnalyticsPeriod.WEEKLY: 604800,  # 1 week
            AnalyticsPeriod.MONTHLY: 2592000,  # 1 month
        }

        self.metric_definitions = {
            "transaction_volume": {"type": MetricType.VOLUME, "unit": "AITBC", "category": "financial"},
            "active_agents": {"type": MetricType.COUNT, "unit": "agents", "category": "agents"},
            "average_price": {"type": MetricType.AVERAGE, "unit": "AITBC", "category": "pricing"},
            "success_rate": {"type": MetricType.PERCENTAGE, "unit": "%", "category": "performance"},
            "supply_demand_ratio": {"type": MetricType.RATIO, "unit": "ratio", "category": "market"},
        }

    async def collect_market_metrics(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> list[MarketMetric]:
        """Collect market metrics for a specific period"""

        metrics = []

        # Collect transaction volume
        volume_metric = await self.collect_transaction_volume(session, period_type, start_time, end_time)
        if volume_metric:
            metrics.append(volume_metric)

        # Collect active agents
        agents_metric = await self.collect_active_agents(session, period_type, start_time, end_time)
        if agents_metric:
            metrics.append(agents_metric)

        # Collect average prices
        price_metric = await self.collect_average_prices(session, period_type, start_time, end_time)
        if price_metric:
            metrics.append(price_metric)

        # Collect success rates
        success_metric = await self.collect_success_rates(session, period_type, start_time, end_time)
        if success_metric:
            metrics.append(success_metric)

        # Collect supply/demand ratio
        ratio_metric = await self.collect_supply_demand_ratio(session, period_type, start_time, end_time)
        if ratio_metric:
            metrics.append(ratio_metric)

        # Store metrics
        for metric in metrics:
            session.add(metric)

        session.commit()

        logger.info(f"Collected {len(metrics)} market metrics for {period_type} period")
        return metrics

    async def collect_transaction_volume(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> MarketMetric | None:
        """Collect transaction volume metrics"""

        # Query trading analytics for transaction volume
        # This would typically query actual transaction data
        # For now, return mock data

        # Mock calculation based on period
        if period_type == AnalyticsPeriod.DAILY:
            volume = 1000.0 + (hash(start_time.date()) % 500)  # Mock variation
        elif period_type == AnalyticsPeriod.WEEKLY:
            volume = 7000.0 + (hash(start_time.isocalendar()[1]) % 1000)
        elif period_type == AnalyticsPeriod.MONTHLY:
            volume = 30000.0 + (hash(start_time.month) % 5000)
        else:
            volume = 100.0

        # Get previous period value for comparison
        previous_start = start_time - (end_time - start_time)
        previous_volume = volume * (0.9 + (hash(previous_start.date()) % 20) / 100.0)  # Mock variation

        change_percentage = ((volume - previous_volume) / previous_volume * 100.0) if previous_volume > 0 else 0.0

        return MarketMetric(
            metric_name="transaction_volume",
            metric_type=MetricType.VOLUME,
            period_type=period_type,
            value=volume,
            previous_value=previous_volume,
            change_percentage=change_percentage,
            unit="AITBC",
            category="financial",
            recorded_at=datetime.now(timezone.utc),
            period_start=start_time,
            period_end=end_time,
            breakdown={
                "by_trade_type": {
                    "ai_power": volume * 0.4,
                    "compute_resources": volume * 0.25,
                    "data_services": volume * 0.15,
                    "model_services": volume * 0.2,
                },
                "by_region": {
                    "us-east": volume * 0.35,
                    "us-west": volume * 0.25,
                    "eu-central": volume * 0.2,
                    "ap-southeast": volume * 0.15,
                    "other": volume * 0.05,
                },
            },
        )

    async def collect_active_agents(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> MarketMetric | None:
        """Collect active agents metrics"""

        # Mock calculation based on period
        if period_type == AnalyticsPeriod.DAILY:
            active_count = 150 + (hash(start_time.date()) % 50)
        elif period_type == AnalyticsPeriod.WEEKLY:
            active_count = 800 + (hash(start_time.isocalendar()[1]) % 100)
        elif period_type == AnalyticsPeriod.MONTHLY:
            active_count = 2500 + (hash(start_time.month) % 500)
        else:
            active_count = 50

        previous_count = active_count * (0.95 + (hash(start_time.date()) % 10) / 100.0)
        change_percentage = ((active_count - previous_count) / previous_count * 100.0) if previous_count > 0 else 0.0

        return MarketMetric(
            metric_name="active_agents",
            metric_type=MetricType.COUNT,
            period_type=period_type,
            value=float(active_count),
            previous_value=float(previous_count),
            change_percentage=change_percentage,
            unit="agents",
            category="agents",
            recorded_at=datetime.now(timezone.utc),
            period_start=start_time,
            period_end=end_time,
            breakdown={
                "by_role": {"buyers": active_count * 0.6, "sellers": active_count * 0.4},
                "by_tier": {
                    "bronze": active_count * 0.3,
                    "silver": active_count * 0.25,
                    "gold": active_count * 0.25,
                    "platinum": active_count * 0.15,
                    "diamond": active_count * 0.05,
                },
                "by_region": {
                    "us-east": active_count * 0.35,
                    "us-west": active_count * 0.25,
                    "eu-central": active_count * 0.2,
                    "ap-southeast": active_count * 0.15,
                    "other": active_count * 0.05,
                },
            },
        )

    async def collect_average_prices(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> MarketMetric | None:
        """Collect average price metrics"""

        # Mock calculation based on period
        base_price = 0.1
        if period_type == AnalyticsPeriod.DAILY:
            avg_price = base_price + (hash(start_time.date()) % 50) / 1000.0
        elif period_type == AnalyticsPeriod.WEEKLY:
            avg_price = base_price + (hash(start_time.isocalendar()[1]) % 100) / 1000.0
        elif period_type == AnalyticsPeriod.MONTHLY:
            avg_price = base_price + (hash(start_time.month) % 200) / 1000.0
        else:
            avg_price = base_price

        previous_price = avg_price * (0.98 + (hash(start_time.date()) % 4) / 100.0)
        change_percentage = ((avg_price - previous_price) / previous_price * 100.0) if previous_price > 0 else 0.0

        return MarketMetric(
            metric_name="average_price",
            metric_type=MetricType.AVERAGE,
            period_type=period_type,
            value=avg_price,
            previous_value=previous_price,
            change_percentage=change_percentage,
            unit="AITBC",
            category="pricing",
            recorded_at=datetime.now(timezone.utc),
            period_start=start_time,
            period_end=end_time,
            breakdown={
                "by_trade_type": {
                    "ai_power": avg_price * 1.2,
                    "compute_resources": avg_price * 0.8,
                    "data_services": avg_price * 0.6,
                    "model_services": avg_price * 1.5,
                },
                "by_tier": {
                    "bronze": avg_price * 0.7,
                    "silver": avg_price * 0.9,
                    "gold": avg_price * 1.1,
                    "platinum": avg_price * 1.3,
                    "diamond": avg_price * 1.6,
                },
            },
        )

    async def collect_success_rates(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> MarketMetric | None:
        """Collect success rate metrics"""

        # Mock calculation based on period
        base_rate = 85.0
        if period_type == AnalyticsPeriod.DAILY:
            success_rate = base_rate + (hash(start_time.date()) % 10) - 5
        elif period_type == AnalyticsPeriod.WEEKLY:
            success_rate = base_rate + (hash(start_time.isocalendar()[1]) % 8) - 4
        elif period_type == AnalyticsPeriod.MONTHLY:
            success_rate = base_rate + (hash(start_time.month) % 6) - 3
        else:
            success_rate = base_rate

        success_rate = max(70.0, min(95.0, success_rate))  # Clamp between 70-95%

        previous_rate = success_rate + (hash(start_time.date()) % 6) - 3
        previous_rate = max(70.0, min(95.0, previous_rate))
        change_percentage = success_rate - previous_rate

        return MarketMetric(
            metric_name="success_rate",
            metric_type=MetricType.PERCENTAGE,
            period_type=period_type,
            value=success_rate,
            previous_value=previous_rate,
            change_percentage=change_percentage,
            unit="%",
            category="performance",
            recorded_at=datetime.now(timezone.utc),
            period_start=start_time,
            period_end=end_time,
            breakdown={
                "by_trade_type": {
                    "ai_power": success_rate + 2,
                    "compute_resources": success_rate - 1,
                    "data_services": success_rate + 1,
                    "model_services": success_rate,
                },
                "by_tier": {
                    "bronze": success_rate - 5,
                    "silver": success_rate - 2,
                    "gold": success_rate,
                    "platinum": success_rate + 2,
                    "diamond": success_rate + 5,
                },
            },
        )

    async def collect_supply_demand_ratio(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> MarketMetric | None:
        """Collect supply/demand ratio metrics"""

        # Mock calculation based on period
        base_ratio = 1.2  # Slightly more supply than demand
        if period_type == AnalyticsPeriod.DAILY:
            ratio = base_ratio + (hash(start_time.date()) % 40) / 100.0 - 0.2
        elif period_type == AnalyticsPeriod.WEEKLY:
            ratio = base_ratio + (hash(start_time.isocalendar()[1]) % 30) / 100.0 - 0.15
        elif period_type == AnalyticsPeriod.MONTHLY:
            ratio = base_ratio + (hash(start_time.month) % 20) / 100.0 - 0.1
        else:
            ratio = base_ratio

        ratio = max(0.5, min(2.0, ratio))  # Clamp between 0.5-2.0

        previous_ratio = ratio + (hash(start_time.date()) % 20) / 100.0 - 0.1
        previous_ratio = max(0.5, min(2.0, previous_ratio))
        change_percentage = ((ratio - previous_ratio) / previous_ratio * 100.0) if previous_ratio > 0 else 0.0

        return MarketMetric(
            metric_name="supply_demand_ratio",
            metric_type=MetricType.RATIO,
            period_type=period_type,
            value=ratio,
            previous_value=previous_ratio,
            change_percentage=change_percentage,
            unit="ratio",
            category="market",
            recorded_at=datetime.now(timezone.utc),
            period_start=start_time,
            period_end=end_time,
            breakdown={
                "by_trade_type": {
                    "ai_power": ratio + 0.1,
                    "compute_resources": ratio - 0.05,
                    "data_services": ratio,
                    "model_services": ratio + 0.05,
                },
                "by_region": {
                    "us-east": ratio - 0.1,
                    "us-west": ratio,
                    "eu-central": ratio + 0.1,
                    "ap-southeast": ratio + 0.05,
                },
            },
        )


class AnalyticsEngine:
    """Advanced analytics and insights engine"""

    def __init__(self):
        self.insight_algorithms = {
            "trend_analysis": self.analyze_trends,
            "anomaly_detection": self.detect_anomalies,
            "opportunity_identification": self.identify_opportunities,
            "risk_assessment": self.assess_risks,
            "performance_analysis": self.analyze_performance,
        }

        self.trend_thresholds = {
            "significant_change": 5.0,  # 5% change is significant
            "strong_trend": 10.0,  # 10% change is strong trend
            "critical_trend": 20.0,  # 20% change is critical
        }

        self.anomaly_thresholds = {
            "statistical": 2.0,  # 2 standard deviations
            "percentage": 15.0,  # 15% deviation
            "volume": 100.0,  # Minimum volume for anomaly detection
        }

    async def generate_insights(
        self, session: Session, period_type: AnalyticsPeriod, start_time: datetime, end_time: datetime
    ) -> list[MarketInsight]:
        """Generate market insights from collected metrics"""

        insights = []

        # Get metrics for analysis
        metrics = session.execute(
            select(MarketMetric)
            .where(
                and_(
                    MarketMetric.period_type == period_type,
                    MarketMetric.period_start >= start_time,
                    MarketMetric.period_end <= end_time,
                )
            )
            .order_by(MarketMetric.recorded_at.desc())
        ).all()

        # Generate trend insights
        trend_insights = await self.analyze_trends(metrics, session)
        insights.extend(trend_insights)

        # Detect anomalies
        anomaly_insights = await self.detect_anomalies(metrics, session)
        insights.extend(anomaly_insights)

        # Identify opportunities
        opportunity_insights = await self.identify_opportunities(metrics, session)
        insights.extend(opportunity_insights)

        # Assess risks
        risk_insights = await self.assess_risks(metrics, session)
        insights.extend(risk_insights)

        # Store insights
        for insight in insights:
            session.add(insight)

        session.commit()

        logger.info(f"Generated {len(insights)} market insights for {period_type} period")
        return insights

    async def analyze_trends(self, metrics: list[MarketMetric], session: Session) -> list[MarketInsight]:
        """Analyze trends in market metrics"""

        insights = []

        for metric in metrics:
            if metric.change_percentage is None:
                continue

            abs_change = abs(metric.change_percentage)

            # Determine trend significance
            if abs_change >= self.trend_thresholds["critical_trend"]:
                trend_type = "critical"
                confidence = 0.9
                impact = "critical"
            elif abs_change >= self.trend_thresholds["strong_trend"]:
                trend_type = "strong"
                confidence = 0.8
                impact = "high"
            elif abs_change >= self.trend_thresholds["significant_change"]:
                trend_type = "significant"
                confidence = 0.7
                impact = "medium"
            else:
                continue  # Skip insignificant changes

            # Determine trend direction
            direction = "increasing" if metric.change_percentage > 0 else "decreasing"

            # Create insight
            insight = MarketInsight(
                insight_type=InsightType.TREND,
                title=f"{trend_type.capitalize()} {direction} trend in {metric.metric_name}",
                description=f"The {metric.metric_name} has {direction} by {abs_change:.1f}% compared to the previous period.",
                confidence_score=confidence,
                impact_level=impact,
                related_metrics=[metric.metric_name],
                time_horizon="short_term",
                analysis_method="statistical",
                data_sources=["market_metrics"],
                recommendations=await self.generate_trend_recommendations(metric, direction, trend_type),
                insight_data={
                    "metric_name": metric.metric_name,
                    "current_value": metric.value,
                    "previous_value": metric.previous_value,
                    "change_percentage": metric.change_percentage,
                    "trend_type": trend_type,
                    "direction": direction,
                },
            )

            insights.append(insight)

        return insights

    async def detect_anomalies(self, metrics: list[MarketMetric], session: Session) -> list[MarketInsight]:
        """Detect anomalies in market metrics"""

        insights = []

        # Get historical data for comparison
        for metric in metrics:
            # Mock anomaly detection based on deviation from expected values
            expected_value = self.calculate_expected_value(metric, session)

            if expected_value is None:
                continue

            deviation_percentage = abs((metric.value - expected_value) / expected_value * 100.0)

            if deviation_percentage >= self.anomaly_thresholds["percentage"]:
                # Anomaly detected
                severity = "critical" if deviation_percentage >= 30.0 else "high" if deviation_percentage >= 20.0 else "medium"
                confidence = min(0.9, deviation_percentage / 50.0)

                insight = MarketInsight(
                    insight_type=InsightType.ANOMALY,
                    title=f"Anomaly detected in {metric.metric_name}",
                    description=f"The {metric.metric_name} value of {metric.value:.2f} deviates by {deviation_percentage:.1f}% from the expected value of {expected_value:.2f}.",
                    confidence_score=confidence,
                    impact_level=severity,
                    related_metrics=[metric.metric_name],
                    time_horizon="immediate",
                    analysis_method="statistical",
                    data_sources=["market_metrics"],
                    recommendations=[
                        "Investigate potential causes for this anomaly",
                        "Monitor related metrics for similar patterns",
                        "Consider if this represents a new market trend",
                    ],
                    insight_data={
                        "metric_name": metric.metric_name,
                        "current_value": metric.value,
                        "expected_value": expected_value,
                        "deviation_percentage": deviation_percentage,
                        "anomaly_type": "statistical_outlier",
                    },
                )

                insights.append(insight)

        return insights

    async def identify_opportunities(self, metrics: list[MarketMetric], session: Session) -> list[MarketInsight]:
        """Identify market opportunities"""

        insights = []

        # Look for supply/demand imbalances
        supply_demand_metric = next((m for m in metrics if m.metric_name == "supply_demand_ratio"), None)

        if supply_demand_metric:
            ratio = supply_demand_metric.value

            if ratio < 0.8:  # High demand, low supply
                insight = MarketInsight(
                    insight_type=InsightType.OPPORTUNITY,
                    title="High demand, low supply opportunity",
                    description=f"The supply/demand ratio of {ratio:.2f} indicates high demand relative to supply. This represents an opportunity for providers.",
                    confidence_score=0.8,
                    impact_level="high",
                    related_metrics=["supply_demand_ratio", "average_price"],
                    time_horizon="medium_term",
                    analysis_method="market_analysis",
                    data_sources=["market_metrics"],
                    recommendations=[
                        "Encourage more providers to enter the market",
                        "Consider price adjustments to balance supply and demand",
                        "Target marketing to attract new sellers",
                    ],
                    suggested_actions=[
                        {"action": "increase_supply", "priority": "high"},
                        {"action": "price_optimization", "priority": "medium"},
                    ],
                    insight_data={
                        "opportunity_type": "supply_shortage",
                        "current_ratio": ratio,
                        "recommended_action": "increase_supply",
                    },
                )

                insights.append(insight)

            elif ratio > 1.5:  # High supply, low demand
                insight = MarketInsight(
                    insight_type=InsightType.OPPORTUNITY,
                    title="High supply, low demand opportunity",
                    description=f"The supply/demand ratio of {ratio:.2f} indicates high supply relative to demand. This represents an opportunity for buyers.",
                    confidence_score=0.8,
                    impact_level="medium",
                    related_metrics=["supply_demand_ratio", "average_price"],
                    time_horizon="medium_term",
                    analysis_method="market_analysis",
                    data_sources=["market_metrics"],
                    recommendations=[
                        "Encourage more buyers to enter the market",
                        "Consider promotional activities to increase demand",
                        "Target marketing to attract new buyers",
                    ],
                    suggested_actions=[
                        {"action": "increase_demand", "priority": "high"},
                        {"action": "promotional_activities", "priority": "medium"},
                    ],
                    insight_data={
                        "opportunity_type": "demand_shortage",
                        "current_ratio": ratio,
                        "recommended_action": "increase_demand",
                    },
                )

                insights.append(insight)

        return insights

    async def assess_risks(self, metrics: list[MarketMetric], session: Session) -> list[MarketInsight]:
        """Assess market risks"""

        insights = []

        # Check for declining success rates
        success_rate_metric = next((m for m in metrics if m.metric_name == "success_rate"), None)

        if success_rate_metric and success_rate_metric.change_percentage is not None:
            if success_rate_metric.change_percentage < -10.0:  # Significant decline
                insight = MarketInsight(
                    insight_type=InsightType.WARNING,
                    title="Declining success rate risk",
                    description=f"The success rate has declined by {abs(success_rate_metric.change_percentage):.1f}% compared to the previous period.",
                    confidence_score=0.8,
                    impact_level="high",
                    related_metrics=["success_rate"],
                    time_horizon="short_term",
                    analysis_method="risk_assessment",
                    data_sources=["market_metrics"],
                    recommendations=[
                        "Investigate causes of declining success rates",
                        "Review quality control processes",
                        "Consider additional verification requirements",
                    ],
                    suggested_actions=[
                        {"action": "investigate_causes", "priority": "high"},
                        {"action": "quality_review", "priority": "medium"},
                    ],
                    insight_data={
                        "risk_type": "performance_decline",
                        "current_rate": success_rate_metric.value,
                        "decline_percentage": success_rate_metric.change_percentage,
                    },
                )

                insights.append(insight)

        return insights

    def calculate_expected_value(self, metric: MarketMetric, session: Session) -> float | None:
        """Calculate expected value for anomaly detection"""

        # Mock implementation - in real system would use historical data
        # For now, use a simple moving average approach

        if metric.metric_name == "transaction_volume":
            return 1000.0  # Expected daily volume
        elif metric.metric_name == "active_agents":
            return 150.0  # Expected daily active agents
        elif metric.metric_name == "average_price":
            return 0.1  # Expected average price
        elif metric.metric_name == "success_rate":
            return 85.0  # Expected success rate
        elif metric.metric_name == "supply_demand_ratio":
            return 1.2  # Expected supply/demand ratio
        else:
            return None

    async def generate_trend_recommendations(self, metric: MarketMetric, direction: str, trend_type: str) -> list[str]:
        """Generate recommendations based on trend analysis"""

        recommendations = []

        if metric.metric_name == "transaction_volume":
            if direction == "increasing":
                recommendations.extend(
                    [
                        "Monitor capacity to handle increased volume",
                        "Consider scaling infrastructure",
                        "Analyze drivers of volume growth",
                    ]
                )
            else:
                recommendations.extend(
                    ["Investigate causes of volume decline", "Consider promotional activities", "Review pricing strategies"]
                )

        elif metric.metric_name == "success_rate":
            if direction == "decreasing":
                recommendations.extend(
                    ["Review quality control processes", "Investigate customer complaints", "Consider additional verification"]
                )
            else:
                recommendations.extend(
                    [
                        "Maintain current quality standards",
                        "Document successful practices",
                        "Share best practices with providers",
                    ]
                )

        elif metric.metric_name == "average_price":
            if direction == "increasing":
                recommendations.extend(
                    ["Monitor market competitiveness", "Consider value proposition", "Analyze price elasticity"]
                )
            else:
                recommendations.extend(["Review pricing strategies", "Monitor profitability", "Consider market positioning"])

        return recommendations


class DashboardManager:
    """Analytics dashboard management and configuration"""

    def __init__(self):
        self.default_widgets = {
            "market_overview": {
                "type": "metric_cards",
                "metrics": ["transaction_volume", "active_agents", "average_price", "success_rate"],
                "layout": {"x": 0, "y": 0, "w": 12, "h": 4},
            },
            "trend_analysis": {
                "type": "line_chart",
                "metrics": ["transaction_volume", "average_price"],
                "layout": {"x": 0, "y": 4, "w": 8, "h": 6},
            },
            "geographic_distribution": {
                "type": "map",
                "metrics": ["active_agents"],
                "layout": {"x": 8, "y": 4, "w": 4, "h": 6},
            },
            "recent_insights": {"type": "insight_list", "limit": 5, "layout": {"x": 0, "y": 10, "w": 12, "h": 4}},
        }

    async def create_default_dashboard(
        self, session: Session, owner_id: str, dashboard_name: str = "Marketplace Analytics"
    ) -> DashboardConfig:
        """Create a default analytics dashboard"""

        dashboard = DashboardConfig(
            dashboard_id=f"dash_{uuid4().hex[:8]}",
            name=dashboard_name,
            description="Default marketplace analytics dashboard",
            dashboard_type="default",
            layout={"columns": 12, "row_height": 30, "margin": [10, 10], "container_padding": [10, 10]},
            widgets=list(self.default_widgets.values()),
            filters=[
                {"name": "time_period", "type": "select", "options": ["daily", "weekly", "monthly"], "default": "daily"},
                {
                    "name": "region",
                    "type": "multiselect",
                    "options": ["us-east", "us-west", "eu-central", "ap-southeast"],
                    "default": [],
                },
            ],
            data_sources=["market_metrics", "trading_analytics", "reputation_data"],
            refresh_interval=300,
            auto_refresh=True,
            owner_id=owner_id,
            viewers=[],
            editors=[],
            is_public=False,
            status="active",
            dashboard_settings={"theme": "light", "animations": True, "auto_refresh": True},
        )

        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)

        logger.info(f"Created default dashboard {dashboard.dashboard_id} for user {owner_id}")
        return dashboard

    async def create_executive_dashboard(self, session: Session, owner_id: str) -> DashboardConfig:
        """Create an executive-level analytics dashboard"""

        executive_widgets = {
            "kpi_summary": {
                "type": "kpi_cards",
                "metrics": ["transaction_volume", "active_agents", "success_rate"],
                "layout": {"x": 0, "y": 0, "w": 12, "h": 3},
            },
            "revenue_trend": {
                "type": "area_chart",
                "metrics": ["transaction_volume"],
                "layout": {"x": 0, "y": 3, "w": 8, "h": 5},
            },
            "market_health": {
                "type": "gauge_chart",
                "metrics": ["success_rate", "supply_demand_ratio"],
                "layout": {"x": 8, "y": 3, "w": 4, "h": 5},
            },
            "top_performers": {
                "type": "leaderboard",
                "entity_type": "agents",
                "metric": "total_earnings",
                "limit": 10,
                "layout": {"x": 0, "y": 8, "w": 6, "h": 4},
            },
            "critical_alerts": {
                "type": "alert_list",
                "severity": ["critical", "high"],
                "limit": 5,
                "layout": {"x": 6, "y": 8, "w": 6, "h": 4},
            },
        }

        dashboard = DashboardConfig(
            dashboard_id=f"exec_{uuid4().hex[:8]}",
            name="Executive Dashboard",
            description="High-level analytics dashboard for executives",
            dashboard_type="executive",
            layout={"columns": 12, "row_height": 30, "margin": [10, 10], "container_padding": [10, 10]},
            widgets=list(executive_widgets.values()),
            filters=[
                {"name": "time_period", "type": "select", "options": ["weekly", "monthly", "quarterly"], "default": "monthly"}
            ],
            data_sources=["market_metrics", "trading_analytics", "reward_analytics"],
            refresh_interval=600,  # 10 minutes for executive dashboard
            auto_refresh=True,
            owner_id=owner_id,
            viewers=[],
            editors=[],
            is_public=False,
            status="active",
            dashboard_settings={"theme": "executive", "animations": False, "compact_mode": True},
        )

        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)

        logger.info(f"Created executive dashboard {dashboard.dashboard_id} for user {owner_id}")
        return dashboard


class MarketplaceAnalytics:
    """Main marketplace analytics service"""

    def __init__(self, session: Session):
        self.session = session
        self.data_collector = DataCollector()
        self.analytics_engine = AnalyticsEngine()
        self.dashboard_manager = DashboardManager()

    async def collect_market_data(self, period_type: AnalyticsPeriod = AnalyticsPeriod.DAILY) -> dict[str, Any]:
        """Collect comprehensive market data"""

        # Calculate time range
        end_time = datetime.now(timezone.utc)

        if period_type == AnalyticsPeriod.DAILY:
            start_time = end_time - timedelta(days=1)
        elif period_type == AnalyticsPeriod.WEEKLY:
            start_time = end_time - timedelta(weeks=1)
        elif period_type == AnalyticsPeriod.MONTHLY:
            start_time = end_time - timedelta(days=30)
        else:
            start_time = end_time - timedelta(hours=1)

        # Collect metrics
        metrics = await self.data_collector.collect_market_metrics(self.session, period_type, start_time, end_time)

        # Generate insights
        insights = await self.analytics_engine.generate_insights(self.session, period_type, start_time, end_time)

        return {
            "period_type": period_type,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "metrics_collected": len(metrics),
            "insights_generated": len(insights),
            "market_data": {
                "transaction_volume": next((m.value for m in metrics if m.metric_name == "transaction_volume"), 0),
                "active_agents": next((m.value for m in metrics if m.metric_name == "active_agents"), 0),
                "average_price": next((m.value for m in metrics if m.metric_name == "average_price"), 0),
                "success_rate": next((m.value for m in metrics if m.metric_name == "success_rate"), 0),
                "supply_demand_ratio": next((m.value for m in metrics if m.metric_name == "supply_demand_ratio"), 0),
            },
        }

    async def generate_insights(self, time_period: str = "daily") -> dict[str, Any]:
        """Generate comprehensive market insights"""

        period_map = {"daily": AnalyticsPeriod.DAILY, "weekly": AnalyticsPeriod.WEEKLY, "monthly": AnalyticsPeriod.MONTHLY}

        period_type = period_map.get(time_period, AnalyticsPeriod.DAILY)

        # Calculate time range
        end_time = datetime.now(timezone.utc)

        if period_type == AnalyticsPeriod.DAILY:
            start_time = end_time - timedelta(days=1)
        elif period_type == AnalyticsPeriod.WEEKLY:
            start_time = end_time - timedelta(weeks=1)
        elif period_type == AnalyticsPeriod.MONTHLY:
            start_time = end_time - timedelta(days=30)
        else:
            start_time = end_time - timedelta(hours=1)

        # Generate insights
        insights = await self.analytics_engine.generate_insights(self.session, period_type, start_time, end_time)

        # Group insights by type
        insight_groups = {}
        for insight in insights:
            insight_type = insight.insight_type.value
            if insight_type not in insight_groups:
                insight_groups[insight_type] = []
            insight_groups[insight_type].append(
                {
                    "id": insight.id,
                    "title": insight.title,
                    "description": insight.description,
                    "confidence": insight.confidence_score,
                    "impact": insight.impact_level,
                    "recommendations": insight.recommendations,
                }
            )

        return {
            "period_type": time_period,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_insights": len(insights),
            "insight_groups": insight_groups,
            "high_impact_insights": len([i for i in insights if i.impact_level in ["high", "critical"]]),
            "high_confidence_insights": len([i for i in insights if i.confidence_score >= 0.8]),
        }

    async def create_dashboard(self, owner_id: str, dashboard_type: str = "default") -> dict[str, Any]:
        """Create analytics dashboard"""

        if dashboard_type == "executive":
            dashboard = await self.dashboard_manager.create_executive_dashboard(self.session, owner_id)
        else:
            dashboard = await self.dashboard_manager.create_default_dashboard(self.session, owner_id)

        return {
            "dashboard_id": dashboard.dashboard_id,
            "name": dashboard.name,
            "type": dashboard.dashboard_type,
            "widgets": len(dashboard.widgets),
            "refresh_interval": dashboard.refresh_interval,
            "created_at": dashboard.created_at.isoformat(),
        }

    async def get_market_overview(self) -> dict[str, Any]:
        """Get comprehensive market overview"""

        # Get latest daily metrics
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)

        metrics = self.session.execute(
            select(MarketMetric)
            .where(
                and_(
                    MarketMetric.period_type == AnalyticsPeriod.DAILY,
                    MarketMetric.period_start >= start_time,
                    MarketMetric.period_end <= end_time,
                )
            )
            .order_by(MarketMetric.recorded_at.desc())
        ).all()

        # Get recent insights
        recent_insights = self.session.execute(
            select(MarketInsight)
            .where(MarketInsight.created_at >= start_time)
            .order_by(MarketInsight.created_at.desc())
            .limit(10)
        ).all()

        # Get active alerts
        active_alerts = self.session.execute(
            select(AnalyticsAlert)
            .where(and_(AnalyticsAlert.status == "active", AnalyticsAlert.created_at >= start_time))
            .order_by(AnalyticsAlert.created_at.desc())
            .limit(5)
        ).all()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "period": "last_24_hours",
            "metrics": {
                metric.metric_name: {
                    "value": metric.value,
                    "change_percentage": metric.change_percentage,
                    "unit": metric.unit,
                    "breakdown": metric.breakdown,
                }
                for metric in metrics
            },
            "insights": [
                {
                    "id": insight.id,
                    "type": insight.insight_type.value,
                    "title": insight.title,
                    "description": insight.description,
                    "confidence": insight.confidence_score,
                    "impact": insight.impact_level,
                }
                for insight in recent_insights
            ],
            "alerts": [
                {
                    "id": alert.id,
                    "title": alert.title,
                    "severity": alert.severity,
                    "message": alert.message,
                    "created_at": alert.created_at.isoformat(),
                }
                for alert in active_alerts
            ],
            "summary": {
                "total_metrics": len(metrics),
                "active_insights": len(recent_insights),
                "active_alerts": len(active_alerts),
                "market_health": "healthy" if len(active_alerts) == 0 else "warning",
            },
        }
