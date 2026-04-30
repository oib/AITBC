"""Integration tests for global infrastructure service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, UTC


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


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Global Infrastructure Service"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "total_regions" in data
    assert "active_regions" in data


@pytest.mark.integration
def test_register_region():
    """Test registering a new region"""
    client = TestClient(app)
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    response = client.post("/api/v1/regions/register", json=region.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "us-west-1"
    assert data["status"] == "registered"


@pytest.mark.integration
def test_register_duplicate_region():
    """Test registering duplicate region"""
    client = TestClient(app)
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    client.post("/api/v1/regions/register", json=region.model_dump())
    
    response = client.post("/api/v1/regions/register", json=region.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_list_regions():
    """Test listing all regions"""
    client = TestClient(app)
    response = client.get("/api/v1/regions")
    assert response.status_code == 200
    data = response.json()
    assert "regions" in data
    assert "total_regions" in data


@pytest.mark.integration
def test_get_region():
    """Test getting specific region"""
    client = TestClient(app)
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    client.post("/api/v1/regions/register", json=region.model_dump())
    
    response = client.get("/api/v1/regions/us-west-1")
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "us-west-1"


@pytest.mark.integration
def test_get_region_not_found():
    """Test getting nonexistent region"""
    client = TestClient(app)
    response = client.get("/api/v1/regions/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_create_deployment():
    """Test creating a deployment"""
    client = TestClient(app)
    # Register region first
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    client.post("/api/v1/regions/register", json=region.model_dump())
    
    deployment = GlobalDeployment(
        deployment_id="deploy_123",
        service_name="test-service",
        target_regions=["us-west-1"],
        configuration={"replicas": 3},
        deployment_strategy="blue_green",
        health_checks=["/health"]
    )
    response = client.post("/api/v1/deployments/create", json=deployment.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["deployment_id"]
    assert data["status"] == "pending"


@pytest.mark.integration
def test_create_deployment_nonexistent_region():
    """Test creating deployment with nonexistent region"""
    client = TestClient(app)
    deployment = GlobalDeployment(
        deployment_id="deploy_123",
        service_name="test-service",
        target_regions=["nonexistent"],
        configuration={"replicas": 3},
        deployment_strategy="blue_green",
        health_checks=["/health"]
    )
    response = client.post("/api/v1/deployments/create", json=deployment.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_get_deployment():
    """Test getting deployment details"""
    client = TestClient(app)
    # Register region first
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    client.post("/api/v1/regions/register", json=region.model_dump())
    
    deployment = GlobalDeployment(
        deployment_id="deploy_123",
        service_name="test-service",
        target_regions=["us-west-1"],
        configuration={"replicas": 3},
        deployment_strategy="blue_green",
        health_checks=["/health"]
    )
    create_response = client.post("/api/v1/deployments/create", json=deployment.model_dump())
    deployment_id = create_response.json()["deployment_id"]
    
    response = client.get(f"/api/v1/deployments/{deployment_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["deployment_id"] == deployment_id


@pytest.mark.integration
def test_list_deployments():
    """Test listing all deployments"""
    client = TestClient(app)
    response = client.get("/api/v1/deployments")
    assert response.status_code == 200
    data = response.json()
    assert "deployments" in data
    assert "total_deployments" in data


@pytest.mark.integration
def test_create_load_balancer():
    """Test creating a load balancer"""
    client = TestClient(app)
    # Register region first
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    client.post("/api/v1/regions/register", json=region.model_dump())
    
    balancer = LoadBalancer(
        balancer_id="lb_123",
        name="Main LB",
        algorithm="round_robin",
        target_regions=["us-west-1"],
        health_check_interval=30,
        failover_threshold=3
    )
    response = client.post("/api/v1/load-balancers/create", json=balancer.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["balancer_id"]
    assert data["status"] == "active"


@pytest.mark.integration
def test_list_load_balancers():
    """Test listing all load balancers"""
    client = TestClient(app)
    response = client.get("/api/v1/load-balancers")
    assert response.status_code == 200
    data = response.json()
    assert "load_balancers" in data
    assert "total_balancers" in data


@pytest.mark.integration
def test_record_performance_metrics():
    """Test recording performance metrics"""
    client = TestClient(app)
    metrics = PerformanceMetrics(
        region_id="us-west-1",
        timestamp=datetime.now(datetime.UTC),
        cpu_usage=50.5,
        memory_usage=60.2,
        network_io=1000.5,
        disk_io=500.3,
        active_connections=100,
        response_time_ms=45.2
    )
    response = client.post("/api/v1/performance/metrics", json=metrics.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["metrics_id"]
    assert data["status"] == "recorded"


@pytest.mark.integration
def test_get_region_performance():
    """Test getting region performance metrics"""
    client = TestClient(app)
    # Record metrics first
    metrics = PerformanceMetrics(
        region_id="us-west-1",
        timestamp=datetime.now(datetime.UTC),
        cpu_usage=50.5,
        memory_usage=60.2,
        network_io=1000.5,
        disk_io=500.3,
        active_connections=100,
        response_time_ms=45.2
    )
    client.post("/api/v1/performance/metrics", json=metrics.model_dump(mode='json'))
    
    response = client.get("/api/v1/performance/us-west-1")
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "us-west-1"
    assert "statistics" in data


@pytest.mark.integration
def test_get_region_compliance():
    """Test getting region compliance information"""
    client = TestClient(app)
    # Register region first
    region = Region(
        region_id="us-west-1",
        name="US West",
        location="North America",
        endpoint="https://us-west-1.api.aitbc.dev",
        status="active",
        capacity=8000,
        current_load=2000,
        latency_ms=50,
        compliance_level="full"
    )
    client.post("/api/v1/regions/register", json=region.model_dump())
    
    response = client.get("/api/v1/compliance/us-west-1")
    assert response.status_code == 200
    data = response.json()
    assert data["region_id"] == "us-west-1"
    assert "compliance_level" in data


@pytest.mark.integration
def test_get_global_dashboard():
    """Test getting global dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/global/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "dashboard" in data
    assert "infrastructure" in data["dashboard"]
