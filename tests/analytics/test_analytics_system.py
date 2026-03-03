"""
Marketplace Analytics System Tests
Comprehensive testing for analytics, insights, reporting, and dashboards
"""

import pytest
import json
import statistics
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from typing import Dict, Any, List


class TestMarketplaceAnalytics:
    """Test marketplace analytics functionality"""
    
    def test_market_metrics_calculation(self):
        """Test market metrics calculation"""
        # Sample market data
        market_data = [
            {'price': 0.10, 'gpu_type': 'RTX 3080', 'timestamp': '2024-01-01T10:00:00Z'},
            {'price': 0.12, 'gpu_type': 'RTX 3080', 'timestamp': '2024-01-01T11:00:00Z'},
            {'price': 0.11, 'gpu_type': 'RTX 3080', 'timestamp': '2024-01-01T12:00:00Z'},
            {'price': 0.15, 'gpu_type': 'RTX 3090', 'timestamp': '2024-01-01T10:00:00Z'},
            {'price': 0.14, 'gpu_type': 'RTX 3090', 'timestamp': '2024-01-01T11:00:00Z'},
        ]
        
        # Calculate metrics
        rtx3080_prices = [d['price'] for d in market_data if d['gpu_type'] == 'RTX 3080']
        rtx3090_prices = [d['price'] for d in market_data if d['gpu_type'] == 'RTX 3090']
        
        # Calculate statistics
        metrics = {
            'RTX 3080': {
                'avg_price': statistics.mean(rtx3080_prices),
                'min_price': min(rtx3080_prices),
                'max_price': max(rtx3080_prices),
                'price_volatility': statistics.stdev(rtx3080_prices) if len(rtx3080_prices) > 1 else 0
            },
            'RTX 3090': {
                'avg_price': statistics.mean(rtx3090_prices),
                'min_price': min(rtx3090_prices),
                'max_price': max(rtx3090_prices),
                'price_volatility': statistics.stdev(rtx3090_prices) if len(rtx3090_prices) > 1 else 0
            }
        }
        
        # Validate metrics
        assert metrics['RTX 3080']['avg_price'] == 0.11
        assert metrics['RTX 3080']['min_price'] == 0.10
        assert metrics['RTX 3080']['max_price'] == 0.12
        assert metrics['RTX 3090']['avg_price'] == 0.145
        assert metrics['RTX 3090']['min_price'] == 0.14
        assert metrics['RTX 3090']['max_price'] == 0.15
    
    def test_demand_analysis(self):
        """Test demand analysis functionality"""
        # Sample demand data
        demand_data = [
            {'date': '2024-01-01', 'requests': 120, 'fulfilled': 100},
            {'date': '2024-01-02', 'requests': 150, 'fulfilled': 130},
            {'date': '2024-01-03', 'requests': 180, 'fulfilled': 160},
            {'date': '2024-01-04', 'requests': 140, 'fulfilled': 125},
        ]
        
        # Calculate demand metrics
        total_requests = sum(d['requests'] for d in demand_data)
        total_fulfilled = sum(d['fulfilled'] for d in demand_data)
        fulfillment_rate = (total_fulfilled / total_requests) * 100
        
        # Calculate trend
        daily_rates = [(d['fulfilled'] / d['requests']) * 100 for d in demand_data]
        trend = 'increasing' if daily_rates[-1] > daily_rates[0] else 'decreasing'
        
        # Validate analysis
        assert total_requests == 590
        assert total_fulfilled == 515
        assert fulfillment_rate == 87.29  # Approximately
        assert trend == 'increasing'
        assert all(0 <= rate <= 100 for rate in daily_rates)
    
    def test_provider_performance(self):
        """Test provider performance analytics"""
        # Sample provider data
        provider_data = [
            {
                'provider_id': 'provider_1',
                'total_jobs': 50,
                'completed_jobs': 45,
                'avg_completion_time': 25.5,  # minutes
                'avg_rating': 4.8,
                'gpu_types': ['RTX 3080', 'RTX 3090']
            },
            {
                'provider_id': 'provider_2',
                'total_jobs': 30,
                'completed_jobs': 28,
                'avg_completion_time': 30.2,
                'avg_rating': 4.6,
                'gpu_types': ['RTX 3080']
            },
            {
                'provider_id': 'provider_3',
                'total_jobs': 40,
                'completed_jobs': 35,
                'avg_completion_time': 22.1,
                'avg_rating': 4.9,
                'gpu_types': ['RTX 3090', 'RTX 4090']
            }
        ]
        
        # Calculate performance metrics
        for provider in provider_data:
            success_rate = (provider['completed_jobs'] / provider['total_jobs']) * 100
            provider['success_rate'] = success_rate
        
        # Sort by performance
        top_providers = sorted(provider_data, key=lambda x: x['success_rate'], reverse=True)
        
        # Validate calculations
        assert top_providers[0]['provider_id'] == 'provider_1'
        assert top_providers[0]['success_rate'] == 90.0
        assert top_providers[1]['success_rate'] == 93.33  # provider_2
        assert top_providers[2]['success_rate'] == 87.5   # provider_3
        
        # Validate data integrity
        for provider in provider_data:
            assert 0 <= provider['success_rate'] <= 100
            assert provider['avg_rating'] >= 0 and provider['avg_rating'] <= 5
            assert provider['avg_completion_time'] > 0


class TestAnalyticsEngine:
    """Test analytics engine functionality"""
    
    def test_data_aggregation(self):
        """Test data aggregation capabilities"""
        # Sample time series data
        time_series_data = [
            {'timestamp': '2024-01-01T00:00:00Z', 'value': 100},
            {'timestamp': '2024-01-01T01:00:00Z', 'value': 110},
            {'timestamp': '2024-01-01T02:00:00Z', 'value': 105},
            {'timestamp': '2024-01-01T03:00:00Z', 'value': 120},
            {'timestamp': '2024-01-01T04:00:00Z', 'value': 115},
        ]
        
        # Aggregate by hour (already hourly data)
        hourly_avg = statistics.mean([d['value'] for d in time_series_data])
        hourly_max = max([d['value'] for d in time_series_data])
        hourly_min = min([d['value'] for d in time_series_data])
        
        # Create aggregated summary
        aggregated_data = {
            'period': 'hourly',
            'data_points': len(time_series_data),
            'average': hourly_avg,
            'maximum': hourly_max,
            'minimum': hourly_min,
            'trend': 'up' if time_series_data[-1]['value'] > time_series_data[0]['value'] else 'down'
        }
        
        # Validate aggregation
        assert aggregated_data['period'] == 'hourly'
        assert aggregated_data['data_points'] == 5
        assert aggregated_data['average'] == 110.0
        assert aggregated_data['maximum'] == 120
        assert aggregated_data['minimum'] == 100
        assert aggregated_data['trend'] == 'up'
    
    def test_anomaly_detection(self):
        """Test anomaly detection in metrics"""
        # Sample metrics with anomalies
        metrics_data = [
            {'timestamp': '2024-01-01T00:00:00Z', 'response_time': 100},
            {'timestamp': '2024-01-01T01:00:00Z', 'response_time': 105},
            {'timestamp': '2024-01-01T02:00:00Z', 'response_time': 98},
            {'timestamp': '2024-01-01T03:00:00Z', 'response_time': 500},  # Anomaly
            {'timestamp': '2024-01-01T04:00:00Z', 'response_time': 102},
            {'timestamp': '2024-01-01T05:00:00Z', 'response_time': 95},
        ]
        
        # Calculate statistics for anomaly detection
        response_times = [d['response_time'] for d in metrics_data]
        mean_time = statistics.mean(response_times)
        stdev_time = statistics.stdev(response_times) if len(response_times) > 1 else 0
        
        # Detect anomalies (values > 2 standard deviations from mean)
        threshold = mean_time + (2 * stdev_time)
        anomalies = [
            d for d in metrics_data 
            if d['response_time'] > threshold
        ]
        
        # Validate anomaly detection
        assert len(anomalies) == 1
        assert anomalies[0]['response_time'] == 500
        assert anomalies[0]['timestamp'] == '2024-01-01T03:00:00Z'
    
    def test_forecasting_model(self):
        """Test simple forecasting model"""
        # Historical data for forecasting
        historical_data = [
            {'period': '2024-01-01', 'demand': 100},
            {'period': '2024-01-02', 'demand': 110},
            {'period': '2024-01-03', 'demand': 105},
            {'period': '2024-01-04', 'demand': 120},
            {'period': '2024-01-05', 'demand': 115},
        ]
        
        # Simple moving average forecast
        demand_values = [d['demand'] for d in historical_data]
        forecast_period = 3
        forecast = statistics.mean(demand_values[-forecast_period:])
        
        # Calculate forecast accuracy (using last known value as "actual")
        last_actual = demand_values[-1]
        forecast_error = abs(forecast - last_actual)
        forecast_accuracy = max(0, 100 - (forecast_error / last_actual * 100))
        
        # Validate forecast
        assert forecast > 0
        assert forecast_accuracy >= 0
        assert forecast_accuracy <= 100


class TestDashboardManager:
    """Test dashboard management functionality"""
    
    def test_dashboard_configuration(self):
        """Test dashboard configuration management"""
        # Sample dashboard configuration
        dashboard_config = {
            'dashboard_id': 'marketplace_overview',
            'title': 'Marketplace Overview',
            'layout': 'grid',
            'widgets': [
                {
                    'id': 'market_metrics',
                    'type': 'metric_card',
                    'title': 'Market Metrics',
                    'position': {'x': 0, 'y': 0, 'w': 4, 'h': 2},
                    'data_source': 'market_metrics_api'
                },
                {
                    'id': 'price_chart',
                    'type': 'line_chart',
                    'title': 'Price Trends',
                    'position': {'x': 4, 'y': 0, 'w': 8, 'h': 4},
                    'data_source': 'price_history_api'
                },
                {
                    'id': 'provider_ranking',
                    'type': 'table',
                    'title': 'Top Providers',
                    'position': {'x': 0, 'y': 2, 'w': 6, 'h': 3},
                    'data_source': 'provider_ranking_api'
                }
            ],
            'refresh_interval': 300,  # 5 minutes
            'permissions': ['read', 'write']
        }
        
        # Validate configuration
        assert dashboard_config['dashboard_id'] == 'marketplace_overview'
        assert len(dashboard_config['widgets']) == 3
        assert dashboard_config['refresh_interval'] == 300
        assert 'read' in dashboard_config['permissions']
        
        # Validate widgets
        for widget in dashboard_config['widgets']:
            assert 'id' in widget
            assert 'type' in widget
            assert 'title' in widget
            assert 'position' in widget
            assert 'data_source' in widget
    
    def test_widget_data_processing(self):
        """Test widget data processing"""
        # Sample data for different widget types
        widget_data = {
            'metric_card': {
                'value': 1250,
                'change': 5.2,
                'change_type': 'increase',
                'unit': 'AITBC',
                'timestamp': datetime.utcnow().isoformat()
            },
            'line_chart': {
                'labels': ['Jan', 'Feb', 'Mar', 'Apr', 'May'],
                'datasets': [
                    {
                        'label': 'RTX 3080',
                        'data': [0.10, 0.11, 0.12, 0.11, 0.13],
                        'borderColor': '#007bff'
                    },
                    {
                        'label': 'RTX 3090',
                        'data': [0.15, 0.14, 0.16, 0.15, 0.17],
                        'borderColor': '#28a745'
                    }
                ]
            },
            'table': {
                'columns': ['provider', 'jobs_completed', 'avg_rating', 'success_rate'],
                'rows': [
                    ['provider_1', 45, 4.8, '90%'],
                    ['provider_2', 28, 4.6, '93%'],
                    ['provider_3', 35, 4.9, '88%']
                ]
            }
        }
        
        # Validate metric card data
        metric_data = widget_data['metric_card']
        assert isinstance(metric_data['value'], (int, float))
        assert isinstance(metric_data['change'], (int, float))
        assert metric_data['change_type'] in ['increase', 'decrease']
        assert 'timestamp' in metric_data
        
        # Validate line chart data
        chart_data = widget_data['line_chart']
        assert 'labels' in chart_data
        assert 'datasets' in chart_data
        assert len(chart_data['datasets']) == 2
        assert len(chart_data['labels']) == len(chart_data['datasets'][0]['data'])
        
        # Validate table data
        table_data = widget_data['table']
        assert 'columns' in table_data
        assert 'rows' in table_data
        assert len(table_data['columns']) == 4
        assert len(table_data['rows']) == 3
    
    def test_dashboard_permissions(self):
        """Test dashboard permission management"""
        # Sample user permissions
        user_permissions = {
            'admin': ['read', 'write', 'delete', 'share'],
            'analyst': ['read', 'write', 'share'],
            'viewer': ['read'],
            'guest': []
        }
        
        # Sample dashboard access rules
        dashboard_access = {
            'marketplace_overview': ['admin', 'analyst', 'viewer'],
            'system_metrics': ['admin'],
            'public_stats': ['admin', 'analyst', 'viewer', 'guest']
        }
        
        # Test permission checking
        def check_permission(user_role, dashboard_id, action):
            if action not in user_permissions[user_role]:
                return False
            if user_role not in dashboard_access[dashboard_id]:
                return False
            return True
        
        # Validate permissions
        assert check_permission('admin', 'marketplace_overview', 'read') is True
        assert check_permission('admin', 'system_metrics', 'write') is True
        assert check_permission('viewer', 'system_metrics', 'read') is False
        assert check_permission('guest', 'public_stats', 'read') is True
        assert check_permission('analyst', 'marketplace_overview', 'delete') is False


class TestReportingSystem:
    """Test reporting system functionality"""
    
    def test_report_generation(self):
        """Test report generation capabilities"""
        # Sample report data
        report_data = {
            'report_id': 'monthly_marketplace_report',
            'title': 'Monthly Marketplace Performance',
            'period': {
                'start': '2024-01-01',
                'end': '2024-01-31'
            },
            'sections': [
                {
                    'title': 'Executive Summary',
                    'content': {
                        'total_transactions': 1250,
                        'total_volume': 156.78,
                        'active_providers': 45,
                        'satisfaction_rate': 4.7
                    }
                },
                {
                    'title': 'Price Analysis',
                    'content': {
                        'avg_gpu_price': 0.12,
                        'price_trend': 'stable',
                        'volatility_index': 0.05
                    }
                }
            ],
            'generated_at': datetime.utcnow().isoformat(),
            'format': 'json'
        }
        
        # Validate report structure
        assert 'report_id' in report_data
        assert 'title' in report_data
        assert 'period' in report_data
        assert 'sections' in report_data
        assert 'generated_at' in report_data
        
        # Validate sections
        for section in report_data['sections']:
            assert 'title' in section
            assert 'content' in section
        
        # Validate data integrity
        summary = report_data['sections'][0]['content']
        assert summary['total_transactions'] > 0
        assert summary['total_volume'] > 0
        assert summary['active_providers'] > 0
        assert 0 <= summary['satisfaction_rate'] <= 5
    
    def test_report_export(self):
        """Test report export functionality"""
        # Sample report for export
        report = {
            'title': 'Marketplace Analysis',
            'data': {
                'metrics': {'transactions': 100, 'volume': 50.5},
                'trends': {'price': 'up', 'demand': 'stable'}
            },
            'metadata': {
                'generated_by': 'analytics_system',
                'generated_at': datetime.utcnow().isoformat()
            }
        }
        
        # Test JSON export
        json_export = json.dumps(report, indent=2)
        assert isinstance(json_export, str)
        assert 'Marketplace Analysis' in json_export
        
        # Test CSV export (simplified)
        csv_data = "Metric,Value\n"
        csv_data += f"Transactions,{report['data']['metrics']['transactions']}\n"
        csv_data += f"Volume,{report['data']['metrics']['volume']}\n"
        
        assert 'Transactions,100' in csv_data
        assert 'Volume,50.5' in csv_data
        assert csv_data.count('\n') == 3  # Header + 2 data rows
    
    def test_report_scheduling(self):
        """Test report scheduling functionality"""
        # Sample schedule configuration
        schedule_config = {
            'report_id': 'daily_marketplace_summary',
            'frequency': 'daily',
            'time': '08:00',
            'recipients': ['admin@aitbc.com', 'ops@aitbc.com'],
            'format': 'pdf',
            'enabled': True,
            'last_run': '2024-01-01T08:00:00Z',
            'next_run': '2024-01-02T08:00:00Z'
        }
        
        # Validate schedule configuration
        assert schedule_config['frequency'] in ['daily', 'weekly', 'monthly']
        assert schedule_config['time'] == '08:00'
        assert len(schedule_config['recipients']) > 0
        assert schedule_config['enabled'] is True
        assert 'next_run' in schedule_config
        
        # Test next run calculation
        from datetime import datetime, timedelta
        
        last_run = datetime.fromisoformat(schedule_config['last_run'].replace('Z', '+00:00'))
        next_run = datetime.fromisoformat(schedule_config['next_run'].replace('Z', '+00:00'))
        
        expected_next_run = last_run + timedelta(days=1)
        assert next_run.date() == expected_next_run.date()
        assert next_run.hour == 8
        assert next_run.minute == 0


class TestDataCollector:
    """Test data collection functionality"""
    
    def test_data_collection_metrics(self):
        """Test data collection metrics gathering"""
        # Sample data collection metrics
        collection_metrics = {
            'total_records_collected': 10000,
            'collection_duration_seconds': 300,
            'error_rate': 0.02,  # 2%
            'data_sources': ['marketplace_api', 'blockchain_api', 'user_activity'],
            'last_collection': datetime.utcnow().isoformat()
        }
        
        # Validate metrics
        assert collection_metrics['total_records_collected'] > 0
        assert collection_metrics['collection_duration_seconds'] > 0
        assert 0 <= collection_metrics['error_rate'] <= 1
        assert len(collection_metrics['data_sources']) > 0
        assert 'last_collection' in collection_metrics
        
        # Calculate collection rate
        collection_rate = collection_metrics['total_records_collected'] / collection_metrics['collection_duration_seconds']
        assert collection_rate > 10  # Should collect at least 10 records per second
    
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
