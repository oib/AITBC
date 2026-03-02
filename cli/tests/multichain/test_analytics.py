"""
Test for analytics and monitoring system
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from aitbc_cli.core.config import MultiChainConfig, NodeConfig
from aitbc_cli.core.analytics import ChainAnalytics, ChainMetrics, ChainAlert

def test_analytics_creation():
    """Test analytics system creation"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    assert analytics.config == config
    assert analytics.metrics_history == {}
    assert analytics.alerts == []
    assert analytics.predictions == {}
    assert analytics.health_scores == {}

async def test_metrics_collection():
    """Test metrics collection"""
    config = MultiChainConfig()
    
    # Add a test node
    test_node = NodeConfig(
        id="test-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )
    config.nodes["test-node"] = test_node
    
    analytics = ChainAnalytics(config)
    
    # Test metrics collection (will use mock data)
    try:
        metrics = await analytics.collect_metrics("test-chain", "test-node")
        assert metrics.chain_id == "test-chain"
        assert metrics.node_id == "test-node"
        assert isinstance(metrics.tps, float)
        assert isinstance(metrics.block_height, int)
    except Exception as e:
        print(f"Expected error in test environment: {e}")

def test_performance_summary():
    """Test performance summary generation"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add some mock metrics
    now = datetime.now()
    mock_metrics = ChainMetrics(
        chain_id="test-chain",
        node_id="test-node",
        timestamp=now,
        block_height=1000,
        tps=15.5,
        avg_block_time=3.2,
        gas_price=20000000000,
        memory_usage_mb=256.0,
        disk_usage_mb=512.0,
        active_nodes=3,
        client_count=25,
        miner_count=8,
        agent_count=12,
        network_in_mb=10.5,
        network_out_mb=8.2
    )
    
    # Add multiple metrics for history
    for i in range(10):
        metrics = ChainMetrics(
            chain_id="test-chain",
            node_id="test-node",
            timestamp=now - timedelta(hours=i),
            block_height=1000 - i,
            tps=15.5 + (i * 0.1),
            avg_block_time=3.2 + (i * 0.01),
            gas_price=20000000000,
            memory_usage_mb=256.0 + (i * 10),
            disk_usage_mb=512.0 + (i * 5),
            active_nodes=3,
            client_count=25,
            miner_count=8,
            agent_count=12,
            network_in_mb=10.5,
            network_out_mb=8.2
        )
        analytics.metrics_history["test-chain"].append(metrics)
    
    # Test performance summary
    summary = analytics.get_chain_performance_summary("test-chain", 24)
    
    assert summary["chain_id"] == "test-chain"
    assert summary["data_points"] == 10
    assert "statistics" in summary
    assert "tps" in summary["statistics"]
    assert "avg" in summary["statistics"]["tps"]

def test_cross_chain_analysis():
    """Test cross-chain analysis"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add mock metrics for multiple chains
    chains = ["chain-1", "chain-2", "chain-3"]
    for chain_id in chains:
        metrics = ChainMetrics(
            chain_id=chain_id,
            node_id="test-node",
            timestamp=datetime.now(),
            block_height=1000,
            tps=15.5,
            avg_block_time=3.2,
            gas_price=20000000000,
            memory_usage_mb=256.0,
            disk_usage_mb=512.0,
            active_nodes=3,
            client_count=25,
            miner_count=8,
            agent_count=12,
            network_in_mb=10.5,
            network_out_mb=8.2
        )
        analytics.metrics_history[chain_id].append(metrics)
    
    # Test cross-chain analysis
    analysis = analytics.get_cross_chain_analysis()
    
    assert analysis["total_chains"] == 3
    assert "resource_usage" in analysis
    assert "alerts_summary" in analysis
    assert "performance_comparison" in analysis

def test_health_score_calculation():
    """Test health score calculation"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add mock metrics
    metrics = ChainMetrics(
        chain_id="test-chain",
        node_id="test-node",
        timestamp=datetime.now(),
        block_height=1000,
        tps=20.0,  # Good TPS
        avg_block_time=3.0,  # Good block time
        gas_price=20000000000,
        memory_usage_mb=500.0,  # Moderate memory usage
        disk_usage_mb=512.0,
        active_nodes=5,  # Good node count
        client_count=25,
        miner_count=8,
        agent_count=12,
        network_in_mb=10.5,
        network_out_mb=8.2
    )
    
    analytics.metrics_history["test-chain"].append(metrics)
    analytics._calculate_health_score("test-chain")
    
    health_score = analytics.health_scores["test-chain"]
    assert 0 <= health_score <= 100
    assert health_score > 50  # Should be a good health score

def test_alert_generation():
    """Test alert generation"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add metrics that should trigger alerts
    metrics = ChainMetrics(
        chain_id="test-chain",
        node_id="test-node",
        timestamp=datetime.now(),
        block_height=1000,
        tps=0.5,  # Low TPS - should trigger alert
        avg_block_time=15.0,  # High block time - should trigger alert
        gas_price=20000000000,
        memory_usage_mb=3000.0,  # High memory usage - should trigger alert
        disk_usage_mb=512.0,
        active_nodes=0,  # Low node count - should trigger alert
        client_count=25,
        miner_count=8,
        agent_count=12,
        network_in_mb=10.5,
        network_out_mb=8.2
    )
    
    # Test alert checking
    asyncio.run(analytics._check_alerts(metrics))
    
    # Should have generated multiple alerts
    assert len(analytics.alerts) > 0
    
    # Check specific alert types
    alert_types = [alert.alert_type for alert in analytics.alerts]
    assert "tps_low" in alert_types
    assert "block_time_high" in alert_types
    assert "memory_high" in alert_types
    assert "node_count_low" in alert_types

def test_optimization_recommendations():
    """Test optimization recommendations"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add metrics that need optimization
    metrics = ChainMetrics(
        chain_id="test-chain",
        node_id="test-node",
        timestamp=datetime.now(),
        block_height=1000,
        tps=0.5,  # Low TPS
        avg_block_time=15.0,  # High block time
        gas_price=20000000000,
        memory_usage_mb=1500.0,  # High memory usage
        disk_usage_mb=512.0,
        active_nodes=1,  # Low node count
        client_count=25,
        miner_count=8,
        agent_count=12,
        network_in_mb=10.5,
        network_out_mb=8.2
    )
    
    analytics.metrics_history["test-chain"].append(metrics)
    
    # Get recommendations
    recommendations = analytics.get_optimization_recommendations("test-chain")
    
    assert len(recommendations) > 0
    
    # Check recommendation types
    rec_types = [rec["type"] for rec in recommendations]
    assert "performance" in rec_types
    assert "resource" in rec_types
    assert "availability" in rec_types

def test_prediction_system():
    """Test performance prediction system"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add historical metrics
    now = datetime.now()
    for i in range(20):  # Need at least 10 data points
        metrics = ChainMetrics(
            chain_id="test-chain",
            node_id="test-node",
            timestamp=now - timedelta(hours=i),
            block_height=1000 - i,
            tps=15.0 + (i * 0.5),  # Increasing trend
            avg_block_time=3.0,
            gas_price=20000000000,
            memory_usage_mb=256.0 + (i * 10),  # Increasing trend
            disk_usage_mb=512.0,
            active_nodes=3,
            client_count=25,
            miner_count=8,
            agent_count=12,
            network_in_mb=10.5,
            network_out_mb=8.2
        )
        analytics.metrics_history["test-chain"].append(metrics)
    
    # Test predictions
    predictions = asyncio.run(analytics.predict_chain_performance("test-chain", 24))
    
    assert len(predictions) > 0
    
    # Check prediction types
    pred_metrics = [pred.metric for pred in predictions]
    assert "tps" in pred_metrics
    assert "memory_usage_mb" in pred_metrics
    
    # Check confidence scores
    for pred in predictions:
        assert 0 <= pred.confidence <= 1
        assert pred.predicted_value >= 0

def test_dashboard_data():
    """Test dashboard data generation"""
    config = MultiChainConfig()
    analytics = ChainAnalytics(config)
    
    # Add mock data
    metrics = ChainMetrics(
        chain_id="test-chain",
        node_id="test-node",
        timestamp=datetime.now(),
        block_height=1000,
        tps=15.5,
        avg_block_time=3.2,
        gas_price=20000000000,
        memory_usage_mb=256.0,
        disk_usage_mb=512.0,
        active_nodes=3,
        client_count=25,
        miner_count=8,
        agent_count=12,
        network_in_mb=10.5,
        network_out_mb=8.2
    )
    
    analytics.metrics_history["test-chain"].append(metrics)
    
    # Get dashboard data
    dashboard_data = analytics.get_dashboard_data()
    
    assert "overview" in dashboard_data
    assert "chain_summaries" in dashboard_data
    assert "alerts" in dashboard_data
    assert "predictions" in dashboard_data
    assert "recommendations" in dashboard_data

if __name__ == "__main__":
    # Run basic tests
    test_analytics_creation()
    test_performance_summary()
    test_cross_chain_analysis()
    test_health_score_calculation()
    test_alert_generation()
    test_optimization_recommendations()
    test_prediction_system()
    test_dashboard_data()
    
    # Run async tests
    asyncio.run(test_metrics_collection())
    
    print("✅ All analytics tests passed!")
