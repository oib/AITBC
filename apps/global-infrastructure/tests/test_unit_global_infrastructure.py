"""Unit tests for global infrastructure service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime


from main import app, Region, GlobalDeployment, LoadBalancer, PerformanceMetrics


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Global Infrastructure Service"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_region_model():
    """Test Region model"""
    region = Region(
        region_id="us-east-1",
        name="US East",
        location="North America",
        endpoint="https://us-east-1.api.aitbc.dev",
        status="active",
        capacity=10000,
        current_load=3500,
        latency_ms=45,
        compliance_level="full"
    )
    assert region.region_id == "us-east-1"
    assert region.name == "US East"
    assert region.status == "active"
    assert region.capacity == 10000
    assert region.compliance_level == "full"


@pytest.mark.unit
def test_global_deployment_model():
    """Test GlobalDeployment model"""
    deployment = GlobalDeployment(
        deployment_id="deploy_123",
        service_name="test-service",
        target_regions=["us-east-1", "eu-west-1"],
        configuration={"replicas": 3},
        deployment_strategy="blue_green",
        health_checks=["/health", "/ready"]
    )
    assert deployment.deployment_id == "deploy_123"
    assert deployment.service_name == "test-service"
    assert deployment.target_regions == ["us-east-1", "eu-west-1"]
    assert deployment.deployment_strategy == "blue_green"


@pytest.mark.unit
def test_load_balancer_model():
    """Test LoadBalancer model"""
    balancer = LoadBalancer(
        balancer_id="lb_123",
        name="Main LB",
        algorithm="round_robin",
        target_regions=["us-east-1", "eu-west-1"],
        health_check_interval=30,
        failover_threshold=3
    )
    assert balancer.balancer_id == "lb_123"
    assert balancer.name == "Main LB"
    assert balancer.algorithm == "round_robin"
    assert balancer.health_check_interval == 30


@pytest.mark.unit
def test_performance_metrics_model():
    """Test PerformanceMetrics model"""
    metrics = PerformanceMetrics(
        region_id="us-east-1",
        timestamp=datetime.utcnow(),
        cpu_usage=50.5,
        memory_usage=60.2,
        network_io=1000.5,
        disk_io=500.3,
        active_connections=100,
        response_time_ms=45.2
    )
    assert metrics.region_id == "us-east-1"
    assert metrics.cpu_usage == 50.5
    assert metrics.memory_usage == 60.2
    assert metrics.active_connections == 100
    assert metrics.response_time_ms == 45.2
