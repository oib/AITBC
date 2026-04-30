"""Integration tests for multi-region load balancer service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, UTC


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


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Multi-Region Load Balancer"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "total_rules" in data


@pytest.mark.integration
def test_create_load_balancing_rule():
    """Test creating a load balancing rule"""
    client = TestClient(app)
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
    response = client.post("/api/v1/rules/create", json=rule.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "rule_123"
    assert data["status"] == "created"


@pytest.mark.integration
def test_create_duplicate_rule():
    """Test creating duplicate load balancing rule"""
    client = TestClient(app)
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
    
    response = client.post("/api/v1/rules/create", json=rule.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_list_load_balancing_rules():
    """Test listing load balancing rules"""
    client = TestClient(app)
    response = client.get("/api/v1/rules")
    assert response.status_code == 200
    data = response.json()
    assert "rules" in data
    assert "total_rules" in data


@pytest.mark.integration
def test_get_load_balancing_rule():
    """Test getting specific load balancing rule"""
    client = TestClient(app)
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
    
    response = client.get("/api/v1/rules/rule_123")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "rule_123"


@pytest.mark.integration
def test_get_load_balancing_rule_not_found():
    """Test getting nonexistent load balancing rule"""
    client = TestClient(app)
    response = client.get("/api/v1/rules/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_update_rule_weights():
    """Test updating rule weights"""
    client = TestClient(app)
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
    client.post("/api/v1/rules/create", json=rule.model_dump())
    
    new_weights = {"us-east-1": 0.7, "eu-west-1": 0.3}
    response = client.post("/api/v1/rules/rule_123/update-weights", json=new_weights)
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "rule_123"
    assert "new_weights" in data


@pytest.mark.integration
def test_update_rule_weights_not_found():
    """Test updating weights for nonexistent rule"""
    client = TestClient(app)
    new_weights = {"us-east-1": 1.0}
    response = client.post("/api/v1/rules/nonexistent/update-weights", json=new_weights)
    assert response.status_code == 404


@pytest.mark.integration
def test_update_rule_weights_zero_total():
    """Test updating weights with zero total"""
    client = TestClient(app)
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
    
    new_weights = {"us-east-1": 0.0}
    response = client.post("/api/v1/rules/rule_123/update-weights", json=new_weights)
    assert response.status_code == 400


@pytest.mark.integration
def test_register_region_health():
    """Test registering region health"""
    client = TestClient(app)
    health = RegionHealth(
        region_id="us-east-1",
        status="healthy",
        response_time_ms=45.5,
        success_rate=0.99,
        active_connections=100,
        last_check=datetime.now(datetime.UTC)
    )
    response = client.post("/api/v1/health/register", json=health.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "us-east-1"


@pytest.mark.integration
def test_get_all_region_health():
    """Test getting all region health"""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "region_health" in data


@pytest.mark.integration
def test_create_geographic_rule():
    """Test creating geographic rule"""
    client = TestClient(app)
    rule = GeographicRule(
        rule_id="geo_123",
        source_regions=["us-east"],
        target_regions=["us-east-1"],
        priority=1,
        latency_threshold_ms=50.0
    )
    response = client.post("/api/v1/geographic-rules/create", json=rule.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "geo_123"
    assert data["status"] == "created"


@pytest.mark.integration
def test_create_duplicate_geographic_rule():
    """Test creating duplicate geographic rule"""
    client = TestClient(app)
    rule = GeographicRule(
        rule_id="geo_123",
        source_regions=["us-east"],
        target_regions=["us-east-1"],
        priority=1,
        latency_threshold_ms=50.0
    )
    client.post("/api/v1/geographic-rules/create", json=rule.model_dump())
    
    response = client.post("/api/v1/geographic-rules/create", json=rule.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_get_optimal_region():
    """Test getting optimal region"""
    client = TestClient(app)
    response = client.get("/api/v1/route/us-east")
    assert response.status_code == 200
    data = response.json()
    assert "client_region" in data
    assert "optimal_region" in data


@pytest.mark.integration
def test_get_optimal_region_with_rule():
    """Test getting optimal region with specific rule"""
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
    
    response = client.get("/api/v1/route/us-east?rule_id=rule_123")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "rule_123"


@pytest.mark.integration
def test_record_balancing_metrics():
    """Test recording balancing metrics"""
    client = TestClient(app)
    metrics = LoadBalancingMetrics(
        balancer_id="lb_123",
        timestamp=datetime.now(datetime.UTC),
        total_requests=1000,
        requests_per_region={"us-east-1": 500},
        average_response_time=50.5,
        error_rate=0.001,
        throughput=100.0
    )
    response = client.post("/api/v1/metrics/record", json=metrics.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["metrics_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_get_balancing_metrics():
    """Test getting balancing metrics"""
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
    
    response = client.get("/api/v1/metrics/rule_123")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "rule_123"


@pytest.mark.integration
def test_get_balancing_metrics_not_found():
    """Test getting metrics for nonexistent rule"""
    client = TestClient(app)
    response = client.get("/api/v1/metrics/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_load_balancing_dashboard():
    """Test getting load balancing dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "dashboard" in data
