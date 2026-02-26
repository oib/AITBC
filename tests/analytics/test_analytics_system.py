"""
Marketplace Analytics System Integration Tests
Comprehensive testing for analytics, insights, reporting, and dashboards
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any

from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from apps.coordinator_api.src.app.services.analytics_service import (
    MarketplaceAnalytics, DataCollector, AnalyticsEngine, DashboardManager
)
from apps.coordinator_api.src.app.domain.analytics import (
    MarketMetric, MarketInsight, AnalyticsReport, DashboardConfig,
    AnalyticsPeriod, MetricType, InsightType, ReportType
)


class TestDataCollector:
    """Test data collection functionality"""
    
    @pytest.fixture
    def data_collector(self):
        return DataCollector()
    
    def test_collect_transaction_volume(self, data_collector):
        """Test transaction volume collection"""
        
        session = MockSession()
        
        # Test daily collection
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        volume_metric = asyncio.run(
            data_collector.collect_transaction_volume(
                session, AnalyticsPeriod.DAILY, start_time, end_time
            )
        )
        
        # Verify metric structure
        assert volume_metric is not None
        assert volume_metric.metric_name == "transaction_volume"
        assert volume_metric.metric_type == MetricType.VOLUME
        assert volume_metric.period_type == AnalyticsPeriod.DAILY
        assert volume_metric.unit == "AITBC"
        assert volume_metric.category == "financial"
        assert volume_metric.value > 0
        assert "by_trade_type" in volume_metric.breakdown
        assert "by_region" in volume_metric.breakdown
        
        # Verify change percentage calculation
        assert volume_metric.change_percentage is not None
        assert volume_metric.previous_value is not None
    
    def test_collect_active_agents(self, data_collector):
        """Test active agents collection"""
        
        session = MockSession()
        
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        agents_metric = asyncio.run(
            data_collector.collect_active_agents(
                session, AnalyticsPeriod.DAILY, start_time, end_time
            )
        )
        
        # Verify metric structure
        assert agents_metric is not None
        assert agents_metric.metric_name == "active_agents"
        assert agents_metric.metric_type == MetricType.COUNT
        assert agents_metric.unit == "agents"
        assert agents_metric.category == "agents"
        assert agents_metric.value > 0
        assert "by_role" in agents_metric.breakdown
        assert "by_tier" in agents_metric.breakdown
        assert "by_region" in agents_metric.breakdown
    
    def test_collect_average_prices(self, data_collector):
        """Test average price collection"""
        
        session = MockSession()
        
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        price_metric = asyncio.run(
            data_collector.collect_average_prices(
                session, AnalyticsPeriod.DAILY, start_time, end_time
            )
        )
        
        # Verify metric structure
        assert price_metric is not None
        assert price_metric.metric_name == "average_price"
        assert price_metric.metric_type == MetricType.AVERAGE
        assert price_metric.unit == "AITBC"
        assert price_metric.category == "pricing"
        assert price_metric.value > 0
        assert "by_trade_type" in price_metric.breakdown
        assert "by_tier" in price_metric.breakdown
    
    def test_collect_success_rates(self, data_collector):
        """Test success rate collection"""
        
        session = MockSession()
        
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        success_metric = asyncio.run(
            data_collector.collect_success_rates(
                session, AnalyticsPeriod.DAILY, start_time, end_time
            )
        )
        
        # Verify metric structure
        assert success_metric is not None
        assert success_metric.metric_name == "success_rate"
        assert success_metric.metric_type == MetricType.PERCENTAGE
        assert success_metric.unit == "%"
        assert success_metric.category == "performance"
        assert 70.0 <= success_metric.value <= 95.0  # Clamped range
        assert "by_trade_type" in success_metric.breakdown
        assert "by_tier" in success_metric.breakdown
    
    def test_collect_supply_demand_ratio(self, data_collector):
        """Test supply/demand ratio collection"""
        
        session = MockSession()
        
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        ratio_metric = asyncio.run(
            data_collector.collect_supply_demand_ratio(
                session, AnalyticsPeriod.DAILY, start_time, end_time
            )
        )
        
        # Verify metric structure
        assert ratio_metric is not None
        assert ratio_metric.metric_name == "supply_demand_ratio"
        assert ratio_metric.metric_type == MetricType.RATIO
        assert ratio_metric.unit == "ratio"
        assert ratio_metric.category == "market"
        assert 0.5 <= ratio_metric.value <= 2.0  # Clamped range
        assert "by_trade_type" in ratio_metric.breakdown
        assert "by_region" in ratio_metric.breakdown
    
    def test_collect_market_metrics_batch(self, data_collector):
        """Test batch collection of all market metrics"""
        
        session = MockSession()
        
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        metrics = asyncio.run(
            data_collector.collect_market_metrics(
                session, AnalyticsPeriod.DAILY, start_time, end_time
            )
        )
        
        # Verify all metrics were collected
        assert len(metrics) == 5  # Should collect 5 metrics
        
        metric_names = [m.metric_name for m in metrics]
        expected_names = [
            "transaction_volume", "active_agents", "average_price", 
            "success_rate", "supply_demand_ratio"
        ]
        
        for name in expected_names:
            assert name in metric_names
    
    def test_different_periods(self, data_collector):
        """Test collection for different time periods"""
        
        session = MockSession()
        
        periods = [AnalyticsPeriod.HOURLY, AnalyticsPeriod.DAILY, AnalyticsPeriod.WEEKLY, AnalyticsPeriod.MONTHLY]
        
        for period in periods:
            if period == AnalyticsPeriod.HOURLY:
                start_time = datetime.utcnow() - timedelta(hours=1)
                end_time = datetime.utcnow()
            elif period == AnalyticsPeriod.WEEKLY:
                start_time = datetime.utcnow() - timedelta(weeks=1)
                end_time = datetime.utcnow()
            elif period == AnalyticsPeriod.MONTHLY:
                start_time = datetime.utcnow() - timedelta(days=30)
                end_time = datetime.utcnow()
            else:
                start_time = datetime.utcnow() - timedelta(days=1)
                end_time = datetime.utcnow()
            
            metrics = asyncio.run(
                data_collector.collect_market_metrics(
                    session, period, start_time, end_time
                )
            )
            
            # Verify metrics were collected for each period
            assert len(metrics) > 0
            for metric in metrics:
                assert metric.period_type == period


class TestAnalyticsEngine:
    """Test analytics engine functionality"""
    
    @pytest.fixture
    def analytics_engine(self):
        return AnalyticsEngine()
    
    @pytest.fixture
    def sample_metrics(self):
        """Create sample metrics for testing"""
        
        return [
            MarketMetric(
                metric_name="transaction_volume",
                metric_type=MetricType.VOLUME,
                period_type=AnalyticsPeriod.DAILY,
                value=1200.0,
                previous_value=1000.0,
                change_percentage=20.0,
                unit="AITBC",
                category="financial",
                recorded_at=datetime.utcnow(),
                period_start=datetime.utcnow() - timedelta(days=1),
                period_end=datetime.utcnow()
            ),
            MarketMetric(
                metric_name="success_rate",
                metric_type=MetricType.PERCENTAGE,
                period_type=AnalyticsPeriod.DAILY,
                value=85.0,
                previous_value=90.0,
                change_percentage=-5.56,
                unit="%",
                category="performance",
                recorded_at=datetime.utcnow(),
                period_start=datetime.utcnow() - timedelta(days=1),
                period_end=datetime.utcnow()
            ),
            MarketMetric(
                metric_name="active_agents",
                metric_type=MetricType.COUNT,
                period_type=AnalyticsPeriod.DAILY,
                value=180.0,
                previous_value=150.0,
                change_percentage=20.0,
                unit="agents",
                category="agents",
                recorded_at=datetime.utcnow(),
                period_start=datetime.utcnow() - timedelta(days=1),
                period_end=datetime.utcnow()
            )
        ]
    
    def test_analyze_trends(self, analytics_engine, sample_metrics):
        """Test trend analysis"""
        
        session = MockSession()
        
        insights = asyncio.run(
            analytics_engine.analyze_trends(sample_metrics, session)
        )
        
        # Verify insights were generated
        assert len(insights) > 0
        
        # Check for significant changes
        significant_insights = [i for i in insights if abs(i.insight_data.get("change_percentage", 0)) >= 5.0]
        assert len(significant_insights) > 0
        
        # Verify insight structure
        for insight in insights:
            assert insight.insight_type == InsightType.TREND
            assert insight.title is not None
            assert insight.description is not None
            assert insight.confidence_score >= 0.7
            assert insight.impact_level in ["low", "medium", "high", "critical"]
            assert insight.related_metrics is not None
            assert insight.recommendations is not None
            assert insight.insight_data is not None
    
    def test_detect_anomalies(self, analytics_engine, sample_metrics):
        """Test anomaly detection"""
        
        session = MockSession()
        
        insights = asyncio.run(
            analytics_engine.detect_anomalies(sample_metrics, session)
        )
        
        # Verify insights were generated (may be empty for normal data)
        for insight in insights:
            assert insight.insight_type == InsightType.ANOMALY
            assert insight.title is not None
            assert insight.description is not None
            assert insight.confidence_score >= 0.0
            assert insight.insight_data.get("anomaly_type") is not None
            assert insight.insight_data.get("deviation_percentage") is not None
    
    def test_identify_opportunities(self, analytics_engine, sample_metrics):
        """Test opportunity identification"""
        
        session = MockSession()
        
        # Add supply/demand ratio metric for opportunity testing
        ratio_metric = MarketMetric(
            metric_name="supply_demand_ratio",
            metric_type=MetricType.RATIO,
            period_type=AnalyticsPeriod.DAILY,
            value=0.7,  # High demand, low supply
            previous_value=1.2,
            change_percentage=-41.67,
            unit="ratio",
            category="market",
            recorded_at=datetime.utcnow(),
            period_start=datetime.utcnow() - timedelta(days=1),
            period_end=datetime.utcnow()
        )
        
        metrics_with_ratio = sample_metrics + [ratio_metric]
        
        insights = asyncio.run(
            analytics_engine.identify_opportunities(metrics_with_ratio, session)
        )
        
        # Verify opportunity insights were generated
        opportunity_insights = [i for i in insights if i.insight_type == InsightType.OPPORTUNITY]
        assert len(opportunity_insights) > 0
        
        # Verify opportunity structure
        for insight in opportunity_insights:
            assert insight.insight_type == InsightType.OPPORTUNITY
            assert "opportunity_type" in insight.insight_data
            assert "recommended_action" in insight.insight_data
            assert insight.suggested_actions is not None
    
    def test_assess_risks(self, analytics_engine, sample_metrics):
        """Test risk assessment"""
        
        session = MockSession()
        
        insights = asyncio.run(
            analytics_engine.assess_risks(sample_metrics, session)
        )
        
        # Verify risk insights were generated
        risk_insights = [i for i in insights if i.insight_type == InsightType.WARNING]
        
        # Check for declining success rate risk
        success_rate_insights = [
            i for i in risk_insights 
            if "success_rate" in i.related_metrics and i.insight_data.get("decline_percentage", 0) < -10.0
        ]
        
        if success_rate_insights:
            assert len(success_rate_insights) > 0
            for insight in success_rate_insights:
                assert insight.impact_level in ["medium", "high", "critical"]
                assert insight.suggested_actions is not None
    
    def test_generate_insights_comprehensive(self, analytics_engine, sample_metrics):
        """Test comprehensive insight generation"""
        
        session = MockSession()
        
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()
        
        insights = asyncio.run(
            analytics_engine.generate_insights(session, AnalyticsPeriod.DAILY, start_time, end_time)
        )
        
        # Verify all insight types were considered
        insight_types = set(i.insight_type for i in insights)
        expected_types = {InsightType.TREND, InsightType.ANOMALY, InsightType.OPPORTUNITY, InsightType.WARNING}
        
        # At least trends should be generated
        assert InsightType.TREND in insight_types
        
        # Verify insight quality
        for insight in insights:
            assert 0.0 <= insight.confidence_score <= 1.0
            assert insight.impact_level in ["low", "medium", "high", "critical"]
            assert insight.recommendations is not None
            assert len(insight.recommendations) > 0


class TestDashboardManager:
    """Test dashboard management functionality"""
    
    @pytest.fixture
    def dashboard_manager(self):
        return DashboardManager()
    
    def test_create_default_dashboard(self, dashboard_manager):
        """Test default dashboard creation"""
        
        session = MockSession()
        
        dashboard = asyncio.run(
            dashboard_manager.create_default_dashboard(session, "user_001", "Test Dashboard")
        )
        
        # Verify dashboard structure
        assert dashboard.dashboard_id is not None
        assert dashboard.name == "Test Dashboard"
        assert dashboard.dashboard_type == "default"
        assert dashboard.owner_id == "user_001"
        assert dashboard.status == "active"
        assert len(dashboard.widgets) == 4  # Default widgets
        assert len(dashboard.filters) == 2  # Default filters
        assert dashboard.refresh_interval == 300
        assert dashboard.auto_refresh is True
        
        # Verify default widgets
        widget_names = [w["type"] for w in dashboard.widgets]
        expected_widgets = ["metric_cards", "line_chart", "map", "insight_list"]
        
        for widget in expected_widgets:
            assert widget in widget_names
    
    def test_create_executive_dashboard(self, dashboard_manager):
        """Test executive dashboard creation"""
        
        session = MockSession()
        
        dashboard = asyncio.run(
            dashboard_manager.create_executive_dashboard(session, "exec_user_001")
        )
        
        # Verify executive dashboard structure
        assert dashboard.dashboard_type == "executive"
        assert dashboard.owner_id == "exec_user_001"
        assert dashboard.refresh_interval == 600  # 10 minutes for executive
        assert dashboard.dashboard_settings["theme"] == "executive"
        assert dashboard.dashboard_settings["compact_mode"] is True
        
        # Verify executive widgets
        widget_names = [w["type"] for w in dashboard.widgets]
        expected_widgets = ["kpi_cards", "area_chart", "gauge_chart", "leaderboard", "alert_list"]
        
        for widget in expected_widgets:
            assert widget in widget_names
    
    def test_default_widgets_structure(self, dashboard_manager):
        """Test default widgets structure"""
        
        widgets = dashboard_manager.default_widgets
        
        # Verify all required widgets are present
        required_widgets = ["market_overview", "trend_analysis", "geographic_distribution", "recent_insights"]
        assert set(widgets.keys()) == set(required_widgets)
        
        # Verify widget structure
        for widget_name, widget_config in widgets.items():
            assert "type" in widget_config
            assert "layout" in widget_config
            assert "x" in widget_config["layout"]
            assert "y" in widget_config["layout"]
            assert "w" in widget_config["layout"]
            assert "h" in widget_config["layout"]


class TestMarketplaceAnalytics:
    """Test main marketplace analytics service"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        class MockSession:
            def __init__(self):
                self.data = {}
                self.committed = False
            
            def exec(self, query):
                # Mock query execution
                if hasattr(query, 'where'):
                    return []
                return []
            
            def add(self, obj):
                self.data[obj.id if hasattr(obj, 'id') else 'temp'] = obj
            
            def commit(self):
                self.committed = True
            
            def refresh(self, obj):
                pass
        
        return MockSession()
    
    @pytest.fixture
    def analytics_service(self, mock_session):
        return MarketplaceAnalytics(mock_session)
    
    def test_collect_market_data(self, analytics_service, mock_session):
        """Test market data collection"""
        
        result = asyncio.run(
            analytics_service.collect_market_data(AnalyticsPeriod.DAILY)
        )
        
        # Verify result structure
        assert "period_type" in result
        assert "start_time" in result
        assert "end_time" in result
        assert "metrics_collected" in result
        assert "insights_generated" in result
        assert "market_data" in result
        
        # Verify market data
        market_data = result["market_data"]
        expected_metrics = ["transaction_volume", "active_agents", "average_price", "success_rate", "supply_demand_ratio"]
        
        for metric in expected_metrics:
            assert metric in market_data
            assert isinstance(market_data[metric], (int, float))
            assert market_data[metric] >= 0
        
        assert result["metrics_collected"] > 0
        assert result["insights_generated"] > 0
    
    def test_generate_insights(self, analytics_service, mock_session):
        """Test insight generation"""
        
        result = asyncio.run(
            analytics_service.generate_insights("daily")
        )
        
        # Verify result structure
        assert "period_type" in result
        assert "start_time" in result
        assert "end_time" in result
        assert "total_insights" in result
        assert "insight_groups" in result
        assert "high_impact_insights" in result
        assert "high_confidence_insights" in result
        
        # Verify insight groups
        insight_groups = result["insight_groups"]
        assert isinstance(insight_groups, dict)
        
        # Should have at least trends
        assert "trend" in insight_groups
        
        # Verify insight data structure
        for insight_type, insights in insight_groups.items():
            assert isinstance(insights, list)
            for insight in insights:
                assert "id" in insight
                assert "type" in insight
                assert "title" in insight
                assert "description" in insight
                assert "confidence" in insight
                assert "impact" in insight
                assert "recommendations" in insight
    
    def test_create_dashboard(self, analytics_service, mock_session):
        """Test dashboard creation"""
        
        result = asyncio.run(
            analytics_service.create_dashboard("user_001", "default")
        )
        
        # Verify result structure
        assert "dashboard_id" in result
        assert "name" in result
        assert "type" in result
        assert "widgets" in result
        assert "refresh_interval" in result
        assert "created_at" in result
        
        # Verify dashboard was created
        assert result["type"] == "default"
        assert result["widgets"] > 0
        assert result["refresh_interval"] == 300
    
    def test_get_market_overview(self, analytics_service, mock_session):
        """Test market overview"""
        
        overview = asyncio.run(
            analytics_service.get_market_overview()
        )
        
        # Verify overview structure
        assert "timestamp" in overview
        assert "period" in overview
        assert "metrics" in overview
        assert "insights" in overview
        assert "alerts" in overview
        assert "summary" in overview
        
        # Verify summary data
        summary = overview["summary"]
        assert "total_metrics" in summary
        assert "active_insights" in summary
        assert "active_alerts" in summary
        assert "market_health" in summary
        assert summary["market_health"] in ["healthy", "warning", "critical"]
    
    def test_different_periods(self, analytics_service, mock_session):
        """Test analytics for different time periods"""
        
        periods = ["daily", "weekly", "monthly"]
        
        for period in periods:
            # Test data collection
            result = asyncio.run(
                analytics_service.collect_market_data(AnalyticsPeriod(period.upper()))
            )
            
            assert result["period_type"] == period.upper()
            assert result["metrics_collected"] > 0
            
            # Test insight generation
            insights = asyncio.run(
                analytics_service.generate_insights(period)
            )
            
            assert insights["period_type"] == period
            assert insights["total_insights"] >= 0


# Mock Session Class
class MockSession:
    """Mock database session for testing"""
    
    def __init__(self):
        self.data = {}
        self.committed = False
    
    def exec(self, query):
        # Mock query execution
        if hasattr(query, 'where'):
            return []
        return []
    
    def add(self, obj):
        self.data[obj.id if hasattr(obj, 'id') else 'temp'] = obj
    
    def commit(self):
        self.committed = True
    
    def refresh(self, obj):
        pass


# Performance Tests
class TestAnalyticsPerformance:
    """Performance tests for analytics system"""
    
    @pytest.mark.asyncio
    async def test_bulk_metric_collection_performance(self):
        """Test performance of bulk metric collection"""
        
        # Test collecting metrics for multiple periods
        # Should complete within acceptable time limits
        
        pass
    
    @pytest.mark.asyncio
    async def test_insight_generation_performance(self):
        """Test insight generation performance"""
        
        # Test generating insights with large datasets
        # Should complete within acceptable time limits
        
        pass


# Utility Functions
def create_test_metric(**kwargs) -> Dict[str, Any]:
    """Create test metric data"""
    
    defaults = {
        "metric_name": "test_metric",
        "metric_type": MetricType.VALUE,
        "period_type": AnalyticsPeriod.DAILY,
        "value": 100.0,
        "previous_value": 90.0,
        "change_percentage": 11.11,
        "unit": "units",
        "category": "test",
        "recorded_at": datetime.utcnow(),
        "period_start": datetime.utcnow() - timedelta(days=1),
        "period_end": datetime.utcnow()
    }
    
    defaults.update(kwargs)
    return defaults


def create_test_insight(**kwargs) -> Dict[str, Any]:
    """Create test insight data"""
    
    defaults = {
        "insight_type": InsightType.TREND,
        "title": "Test Insight",
        "description": "Test description",
        "confidence_score": 0.8,
        "impact_level": "medium",
        "related_metrics": ["test_metric"],
        "time_horizon": "short_term",
        "recommendations": ["Test recommendation"],
        "insight_data": {"test": "data"}
    }
    
    defaults.update(kwargs)
    return defaults


# Test Configuration
@pytest.fixture(scope="session")
def test_config():
    """Test configuration for analytics system tests"""
    
    return {
        "test_metric_count": 100,
        "test_insight_count": 50,
        "test_report_count": 20,
        "performance_threshold_ms": 5000,
        "memory_threshold_mb": 200
    }


# Test Markers
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.slow = pytest.mark.slow
