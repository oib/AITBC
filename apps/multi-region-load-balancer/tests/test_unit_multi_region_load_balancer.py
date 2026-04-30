"""Unit tests for multi-region load balancer service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime, UTC


from main import app, LoadBalancingRule, RegionHealth, LoadBalancingMetrics, GeographicRule


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Multi-Region Load Balancer"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_load_balancing_rule_model():
    """Test LoadBalancingRule model"""
    rule = LoadBalancingRule(
        rule_id="rule_123",
        name="Test Rule",
        algorithm="weighted_round_robin",
        target_regions=["us-east-1", "eu-west-1"],
        weights={"us-east-1": 0.5, "eu-west-1": 0.5},
        health_check_path="/health",
        failover_enabled=True,
        session_affinity=False
    )
    assert rule.rule_id == "rule_123"
    assert rule.name == "Test Rule"
    assert rule.algorithm == "weighted_round_robin"
    assert rule.failover_enabled is True
    assert rule.session_affinity is False


@pytest.mark.unit
def test_region_health_model():
    """Test RegionHealth model"""
    health = RegionHealth(
        region_id="us-east-1",
        status="healthy",
        response_time_ms=45.5,
        success_rate=0.99,
        active_connections=100,
        last_check=datetime.now(datetime.UTC)
    )
    assert health.region_id == "us-east-1"
    assert health.status == "healthy"
    assert health.response_time_ms == 45.5
    assert health.success_rate == 0.99
    assert health.active_connections == 100


@pytest.mark.unit
def test_load_balancing_metrics_model():
    """Test LoadBalancingMetrics model"""
    metrics = LoadBalancingMetrics(
        balancer_id="lb_123",
        timestamp=datetime.now(datetime.UTC),
        total_requests=1000,
        requests_per_region={"us-east-1": 500, "eu-west-1": 500},
        average_response_time=50.5,
        error_rate=0.001,
        throughput=100.0
    )
    assert metrics.balancer_id == "lb_123"
    assert metrics.total_requests == 1000
    assert metrics.average_response_time == 50.5
    assert metrics.error_rate == 0.001


@pytest.mark.unit
def test_geographic_rule_model():
    """Test GeographicRule model"""
    rule = GeographicRule(
        rule_id="geo_123",
        source_regions=["us-east", "us-west"],
        target_regions=["us-east-1", "us-west-1"],
        priority=1,
        latency_threshold_ms=50.0
    )
    assert rule.rule_id == "geo_123"
    assert rule.source_regions == ["us-east", "us-west"]
    assert rule.priority == 1
    assert rule.latency_threshold_ms == 50.0


@pytest.mark.unit
def test_load_balancing_rule_empty_weights():
    """Test LoadBalancingRule with empty weights"""
    rule = LoadBalancingRule(
        rule_id="rule_123",
        name="Test Rule",
        algorithm="round_robin",
        target_regions=["us-east-1"],
        weights={},
        health_check_path="/health",
        failover_enabled=False,
        session_affinity=False
    )
    assert rule.weights == {}


@pytest.mark.unit
def test_region_health_negative_response_time():
    """Test RegionHealth with negative response time"""
    health = RegionHealth(
        region_id="us-east-1",
        status="healthy",
        response_time_ms=-45.5,
        success_rate=0.99,
        active_connections=100,
        last_check=datetime.now(datetime.UTC)
    )
    assert health.response_time_ms == -45.5
