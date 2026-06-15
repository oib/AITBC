"""
Core Analytics Tests
Tests for chain analytics and monitoring system
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest


class TestChainMetrics:
    """Test ChainMetrics dataclass"""

    def test_chain_metrics_creation(self):
        """Test creating ChainMetrics"""
        from aitbc_cli.core.analytics import ChainMetrics

        metrics = ChainMetrics(
            chain_id="aitbc-main",
            node_id="node123",
            timestamp=datetime.now(),
            block_height=1000,
            tps=10.5,
            avg_block_time=2.5,
            gas_price=100,
            memory_usage_mb=512.0,
            disk_usage_mb=1024.0,
            active_nodes=5,
            client_count=10,
            miner_count=3,
            agent_count=7,
            network_in_mb=100.0,
            network_out_mb=50.0,
        )

        assert metrics.chain_id == "aitbc-main"
        assert metrics.tps == 10.5
        assert metrics.block_height == 1000


class TestChainAlert:
    """Test ChainAlert dataclass"""

    def test_chain_alert_creation(self):
        """Test creating ChainAlert"""
        from aitbc_cli.core.analytics import ChainAlert

        alert = ChainAlert(
            chain_id="aitbc-main",
            alert_type="tps_low",
            severity="warning",
            message="TPS below threshold",
            timestamp=datetime.now(),
            threshold=5.0,
            current_value=2.5,
        )

        assert alert.chain_id == "aitbc-main"
        assert alert.alert_type == "tps_low"
        assert alert.severity == "warning"


class TestChainPrediction:
    """Test ChainPrediction dataclass"""

    def test_chain_prediction_creation(self):
        """Test creating ChainPrediction"""
        from aitbc_cli.core.analytics import ChainPrediction

        prediction = ChainPrediction(
            chain_id="aitbc-main",
            metric="tps",
            predicted_value=15.0,
            confidence=0.85,
            time_horizon_hours=24,
            created_at=datetime.now(),
        )

        assert prediction.chain_id == "aitbc-main"
        assert prediction.metric == "tps"
        assert prediction.confidence == 0.85


class TestChainAnalytics:
    """Test ChainAnalytics class"""

    @patch("aitbc_cli.core.analytics.NodeClient")
    def test_init(self, mock_node_client):
        """Test ChainAnalytics initialization"""
        from aitbc_cli.core.analytics import ChainAnalytics, MultiChainConfig

        config = Mock(spec=MultiChainConfig)
        analytics = ChainAnalytics(config)

        assert analytics.config == config
        assert analytics.alerts == []
        assert analytics.health_scores == {}
        assert "tps_low" in analytics.thresholds
        assert analytics.thresholds["tps_low"] == 1.0

    @patch("aitbc_cli.core.analytics.NodeClient")
    def test_thresholds(self, mock_node_client):
        """Test alert thresholds"""
        from aitbc_cli.core.analytics import ChainAnalytics, MultiChainConfig

        config = Mock(spec=MultiChainConfig)
        analytics = ChainAnalytics(config)

        assert analytics.thresholds["tps_low"] == 1.0
        assert analytics.thresholds["tps_high"] == 100.0
        assert analytics.thresholds["block_time_high"] == 10.0
        assert analytics.thresholds["memory_usage_high"] == 80.0
        assert analytics.thresholds["disk_usage_high"] == 85.0
        assert analytics.thresholds["node_count_low"] == 1
        assert analytics.thresholds["client_count_low"] == 5

    @patch("aitbc_cli.core.analytics.NodeClient")
    def test_health_scores_initialization(self, mock_node_client):
        """Test health scores initialization"""
        from aitbc_cli.core.analytics import ChainAnalytics, MultiChainConfig

        config = Mock(spec=MultiChainConfig)
        analytics = ChainAnalytics(config)

        assert isinstance(analytics.health_scores, dict)
        assert len(analytics.health_scores) == 0

    @patch("aitbc_cli.core.analytics.NodeClient")
    def test_metrics_history_initialization(self, mock_node_client):
        """Test metrics history initialization"""
        from aitbc_cli.core.analytics import ChainAnalytics, MultiChainConfig

        config = Mock(spec=MultiChainConfig)
        analytics = ChainAnalytics(config)

        assert isinstance(analytics.metrics_history, dict)
        assert len(analytics.metrics_history) == 0

    @patch("aitbc_cli.core.analytics.NodeClient")
    def test_alerts_initialization(self, mock_node_client):
        """Test alerts initialization"""
        from aitbc_cli.core.analytics import ChainAnalytics, MultiChainConfig

        config = Mock(spec=MultiChainConfig)
        analytics = ChainAnalytics(config)

        assert isinstance(analytics.alerts, list)
        assert len(analytics.alerts) == 0

    @patch("aitbc_cli.core.analytics.NodeClient")
    def test_predictions_initialization(self, mock_node_client):
        """Test predictions initialization"""
        from aitbc_cli.core.analytics import ChainAnalytics, MultiChainConfig

        config = Mock(spec=MultiChainConfig)
        analytics = ChainAnalytics(config)

        assert isinstance(analytics.predictions, dict)
        assert len(analytics.predictions) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
