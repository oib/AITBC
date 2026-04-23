"""Edge case and error handling tests for global infrastructure service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime


from main import app, Region, GlobalDeployment, LoadBalancer, PerformanceMetrics, global_regions, deployments, load_balancers, performance_metrics


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    global_regions.clear()
    deployments.clear()
    load_balancers.clear()
    performance_metrics.clear()
    yield
    global_regions.clear()
    deployments.clear()
    load_balancers.clear()
    performance_metrics.clear()


@pytest.mark.unit
def test_region_negative_capacity():
    """Test Region with negative capacity"""
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=-1000,
        current_load=-500,
        latency_ms=-50,
        compliance_level="full"
    )
    assert region.capacity == -1000
    assert region.current_load == -500


@pytest.mark.unit
def test_region_empty_name():
    """Test Region with empty name"""
    region = Region(
        region_id="us-west-1",
        name="",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    assert region.name == ""


@pytest.mark.unit
def test_deployment_empty_target_regions():
    """Test GlobalDeployment with empty target regions"""
    deployment = GlobalDeployment(
        deployment_id="deploy_123",
        service_name="test-service",
        target_regions=[],
        configuration={},
        deployment_strategy="blue_green",
        health_checks=[]
    )
    assert deployment.target_regions == []


@pytest.mark.unit
def test_load_balancer_negative_health_check_interval():
    """Test LoadBalancer with negative health check interval"""
    balancer = LoadBalancer(
        balancer_id="lb_123",
        name="Main LB",
        algorithm="round_robin",
        target_regions=["us-east-1"],
        health_check_interval=-30,
        failover_threshold=3
    )
    assert balancer.health_check_interval == -30


@pytest.mark.unit
def test_performance_metrics_negative_values():
    """Test PerformanceMetrics with negative values"""
    metrics = PerformanceMetrics(
        region_id="us-east-1",
        timestamp=datetime.utcnow(),
        cpu_usage=-50.5,
        memory_usage=-60.2,
        network_io=-1000.5,
        disk_io=-500.3,
        active_connections=-100,
        response_time_ms=-45.2
    )
    assert metrics.cpu_usage == -50.5
    assert metrics.active_connections == -100


@pytest.mark.integration
def test_list_regions_with_no_regions():
    """Test listing regions when no regions exist"""
    client = TestClient(app)
    response = client.get("/api/v1/regions")
    assert response.status_code == 200
    data = response.json()
    assert data["total_regions"] == 0


@pytest.mark.integration
def test_list_deployments_with_no_deployments():
    """Test listing deployments when no deployments exist"""
    client = TestClient(app)
    response = client.get("/api/v1/deployments")
    assert response.status_code == 200
    data = response.json()
    assert data["total_deployments"] == 0


@pytest.mark.integration
def test_list_load_balancers_with_no_balancers():
    """Test listing load balancers when no balancers exist"""
    client = TestClient(app)
    response = client.get("/api/v1/load-balancers")
    assert response.status_code == 200
    data = response.json()
    assert data["total_balancers"] == 0


@pytest.mark.integration
def test_get_deployment_not_found():
    """Test getting nonexistent deployment"""
    client = TestClient(app)
    response = client.get("/api/v1/deployments/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_region_performance_no_data():
    """Test getting region performance when no data exists"""
    client = TestClient(app)
    response = client.get("/api/v1/performance/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_region_compliance_nonexistent():
    """Test getting compliance for nonexistent region"""
    client = TestClient(app)
    response = client.get("/api/v1/compliance/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_create_load_balancer_nonexistent_region():
    """Test creating load balancer with nonexistent region"""
    client = TestClient(app)
    balancer = LoadBalancer(
        balancer_id="lb_123",
        name="Main LB",
        algorithm="round_robin",
        target_regions=["nonexistent"],
        health_check_interval=30,
        failover_threshold=3
    )
    response = client.post("/api/v1/load-balancers/create", json=balancer.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_list_deployments_with_status_filter():
    """Test listing deployments with status filter"""
    client = TestClient(app)
    response = client.get("/api/v1/deployments?status=pending")
    assert response.status_code == 200
    data = response.json()
    assert "status_filter" in data


@pytest.mark.integration
def test_global_dashboard_with_no_data():
    """Test global dashboard with no data"""
    client = TestClient(app)
    response = client.get("/api/v1/global/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["dashboard"]["infrastructure"]["total_regions"] == 0
