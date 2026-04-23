"""Edge case and error handling tests for multi-region load balancer service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime


from main import app, LoadBalancingRule, RegionHealth, LoadBalancingMetrics, GeographicRule, load_balancing_rules, region_health_status, balancing_metrics, geographic_rules


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    load_balancing_rules.clear()
    region_health_status.clear()
    balancing_metrics.clear()
    geographic_rules.clear()
    yield
    load_balancing_rules.clear()
    region_health_status.clear()
    balancing_metrics.clear()
    geographic_rules.clear()


@pytest.mark.unit
def test_load_balancing_rule_empty_target_regions():
    """Test LoadBalancingRule with empty target regions"""
    rule = LoadBalancingRule(
        rule_id="rule_123",
        name="Test Rule",
        algorithm="round_robin",
        target_regions=[],
        weights={},
        health_check_path="/health",
        failover_enabled=False,
        session_affinity=False
    )
    assert rule.target_regions == []


@pytest.mark.unit
def test_region_health_negative_success_rate():
    """Test RegionHealth with negative success rate"""
    health = RegionHealth(
        region_id="us-east-1",
        status="healthy",
        response_time_ms=45.5,
        success_rate=-0.5,
        active_connections=100,
        last_check=datetime.utcnow()
    )
    assert health.success_rate == -0.5


@pytest.mark.unit
def test_region_health_negative_connections():
    """Test RegionHealth with negative connections"""
    health = RegionHealth(
        region_id="us-east-1",
        status="healthy",
        response_time_ms=45.5,
        success_rate=0.99,
        active_connections=-100,
        last_check=datetime.utcnow()
    )
    assert health.active_connections == -100


@pytest.mark.unit
def test_load_balancing_metrics_negative_requests():
    """Test LoadBalancingMetrics with negative requests"""
    metrics = LoadBalancingMetrics(
        balancer_id="lb_123",
        timestamp=datetime.utcnow(),
        total_requests=-1000,
        requests_per_region={},
        average_response_time=50.5,
        error_rate=0.001,
        throughput=100.0
    )
    assert metrics.total_requests == -1000


@pytest.mark.unit
def test_load_balancing_metrics_negative_response_time():
    """Test LoadBalancingMetrics with negative response time"""
    metrics = LoadBalancingMetrics(
        balancer_id="lb_123",
        timestamp=datetime.utcnow(),
        total_requests=1000,
        requests_per_region={},
        average_response_time=-50.5,
        error_rate=0.001,
        throughput=100.0
    )
    assert metrics.average_response_time == -50.5


@pytest.mark.unit
def test_geographic_rule_empty_source_regions():
    """Test GeographicRule with empty source regions"""
    rule = GeographicRule(
        rule_id="geo_123",
        source_regions=[],
        target_regions=["us-east-1"],
        priority=1,
        latency_threshold_ms=50.0
    )
    assert rule.source_regions == []


@pytest.mark.unit
def test_geographic_rule_negative_priority():
    """Test GeographicRule with negative priority"""
    rule = GeographicRule(
        rule_id="geo_123",
        source_regions=["us-east"],
        target_regions=["us-east-1"],
        priority=-5,
        latency_threshold_ms=50.0
    )
    assert rule.priority == -5


@pytest.mark.unit
def test_geographic_rule_negative_latency_threshold():
    """Test GeographicRule with negative latency threshold"""
    rule = GeographicRule(
        rule_id="geo_123",
        source_regions=["us-east"],
        target_regions=["us-east-1"],
        priority=1,
        latency_threshold_ms=-50.0
    )
    assert rule.latency_threshold_ms == -50.0


@pytest.mark.integration
def test_list_rules_with_no_rules():
    """Test listing rules when no rules exist"""
    client = TestClient(app)
    response = client.get("/api/v1/rules")
    assert response.status_code == 200
    data = response.json()
    assert data["total_rules"] == 0


@pytest.mark.integration
def test_get_region_health_with_no_regions():
    """Test getting region health when no regions exist"""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["total_regions"] == 0


@pytest.mark.integration
def test_get_balancing_metrics_hours_parameter():
    """Test getting balancing metrics with custom hours parameter"""
    client = TestClient(app)
    # Create a rule first
    rule = LoadBalancingRule(
        rule_id="rule_123",
        name="Test Rule",
        algorithm="weighted_round_robin",
        target_regions=["us-east-1"],
        weights={"us-east-1": 1.0},
        health_check_path="/health",
        failover_enabled=True,
        session_affinity=False
    )
    client.post("/api/v1/rules/create", json=rule.model_dump())
    
    response = client.get("/api/v1/metrics/rule_123?hours=12")
    assert response.status_code == 200
    data = response.json()
    assert data["period_hours"] == 12


@pytest.mark.integration
def test_get_optimal_region_nonexistent_rule():
    """Test getting optimal region with nonexistent rule"""
    client = TestClient(app)
    response = client.get("/api/v1/route/us-east?rule_id=nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_dashboard_with_no_data():
    """Test dashboard with no data"""
    client = TestClient(app)
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["dashboard"]["overview"]["total_rules"] == 0
