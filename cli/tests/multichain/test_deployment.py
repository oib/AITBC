"""
Test for production deployment and scaling system
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from aitbc_cli.core.deployment import (
    ProductionDeployment, DeploymentConfig, DeploymentMetrics,
    ScalingEvent, ScalingPolicy, DeploymentStatus
)

def test_deployment_creation():
    """Test deployment system creation"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    assert deployment.config_path == Path("/tmp/test_aitbc")
    assert deployment.deployments == {}
    assert deployment.metrics == {}
    assert deployment.scaling_events == []
    assert deployment.health_checks == {}
    
    # Check directories were created
    assert deployment.deployment_dir.exists()
    assert deployment.config_dir.exists()
    assert deployment.logs_dir.exists()
    assert deployment.backups_dir.exists()

async def test_create_deployment_config():
    """Test deployment configuration creation"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Create deployment
    deployment_id = await deployment.create_deployment(
        name="test-deployment",
        environment="production",
        region="us-west-1",
        instance_type="t3.medium",
        min_instances=1,
        max_instances=10,
        desired_instances=2,
        port=8080,
        domain="test.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc"}
    )
    
    assert deployment_id is not None
    assert deployment_id in deployment.deployments
    
    config = deployment.deployments[deployment_id]
    assert config.name == "test-deployment"
    assert config.environment == "production"
    assert config.min_instances == 1
    assert config.max_instances == 10
    assert config.desired_instances == 2
    assert config.scaling_policy == ScalingPolicy.AUTO
    assert config.port == 8080
    assert config.domain == "test.aitbc.dev"

async def test_deployment_application():
    """Test application deployment"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Create deployment first
    deployment_id = await deployment.create_deployment(
        name="test-app",
        environment="staging",
        region="us-east-1",
        instance_type="t3.small",
        min_instances=1,
        max_instances=5,
        desired_instances=2,
        port=3000,
        domain="staging.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc_staging"}
    )
    
    # Mock the infrastructure deployment (skip actual system calls)
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        print(f"Mock infrastructure deployment for {dep_config.name}")
        return True
    
    deployment._deploy_infrastructure = mock_deploy_infra
    
    # Deploy application
    success = await deployment.deploy_application(deployment_id)
    
    assert success
    assert deployment_id in deployment.health_checks
    assert deployment.health_checks[deployment_id] == True
    assert deployment_id in deployment.metrics
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra

async def test_manual_scaling():
    """Test manual scaling"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Create deployment
    deployment_id = await deployment.create_deployment(
        name="scale-test",
        environment="production",
        region="us-west-2",
        instance_type="t3.medium",
        min_instances=1,
        max_instances=10,
        desired_instances=2,
        port=8080,
        domain="scale.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc"}
    )
    
    # Mock infrastructure deployment
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        return True
    deployment._deploy_infrastructure = mock_deploy_infra
    
    # Deploy first
    await deployment.deploy_application(deployment_id)
    
    # Scale up
    success = await deployment.scale_deployment(deployment_id, 5, "manual scaling test")
    
    assert success
    
    # Check deployment was updated
    config = deployment.deployments[deployment_id]
    assert config.desired_instances == 5
    
    # Check scaling event was created
    scaling_events = [e for e in deployment.scaling_events if e.deployment_id == deployment_id]
    assert len(scaling_events) > 0
    
    latest_event = scaling_events[-1]
    assert latest_event.old_instances == 2
    assert latest_event.new_instances == 5
    assert latest_event.success == True
    assert latest_event.trigger_reason == "manual scaling test"
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra

async def test_auto_scaling():
    """Test automatic scaling"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Create deployment
    deployment_id = await deployment.create_deployment(
        name="auto-scale-test",
        environment="production",
        region="us-east-1",
        instance_type="t3.medium",
        min_instances=1,
        max_instances=10,
        desired_instances=2,
        port=8080,
        domain="autoscale.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc"}
    )
    
    # Mock infrastructure deployment
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        return True
    deployment._deploy_infrastructure = mock_deploy_infra
    
    # Deploy first
    await deployment.deploy_application(deployment_id)
    
    # Set metrics to trigger scale up (high CPU)
    metrics = deployment.metrics[deployment_id]
    metrics.cpu_usage = 85.0  # Above threshold
    metrics.memory_usage = 40.0
    metrics.error_rate = 1.0
    metrics.response_time = 500.0
    
    # Trigger auto-scaling
    success = await deployment.auto_scale_deployment(deployment_id)
    
    assert success
    
    # Check deployment was scaled up
    config = deployment.deployments[deployment_id]
    assert config.desired_instances == 3  # Should have scaled up by 1
    
    # Set metrics to trigger scale down
    metrics.cpu_usage = 15.0  # Below threshold
    metrics.memory_usage = 25.0
    
    # Trigger auto-scaling again
    success = await deployment.auto_scale_deployment(deployment_id)
    
    assert success
    
    # Check deployment was scaled down
    config = deployment.deployments[deployment_id]
    assert config.desired_instances == 2  # Should have scaled down by 1
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra

async def test_deployment_status():
    """Test deployment status retrieval"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Create and deploy
    deployment_id = await deployment.create_deployment(
        name="status-test",
        environment="production",
        region="us-west-1",
        instance_type="t3.medium",
        min_instances=1,
        max_instances=5,
        desired_instances=2,
        port=8080,
        domain="status.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc"}
    )
    
    # Mock infrastructure deployment
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        return True
    deployment._deploy_infrastructure = mock_deploy_infra
    
    await deployment.deploy_application(deployment_id)
    
    # Get status
    status = await deployment.get_deployment_status(deployment_id)
    
    assert status is not None
    assert "deployment" in status
    assert "metrics" in status
    assert "health_status" in status
    assert "recent_scaling_events" in status
    assert "uptime_percentage" in status
    
    # Check deployment info
    deployment_info = status["deployment"]
    assert deployment_info["name"] == "status-test"
    assert deployment_info["environment"] == "production"
    assert deployment_info["desired_instances"] == 2
    
    # Check health status
    assert status["health_status"] == True
    
    # Check metrics
    metrics = status["metrics"]
    assert metrics["deployment_id"] == deployment_id
    assert metrics["cpu_usage"] >= 0
    assert metrics["memory_usage"] >= 0
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra

async def test_cluster_overview():
    """Test cluster overview"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Mock infrastructure deployment
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        return True
    deployment._deploy_infrastructure = mock_deploy_infra
    
    # Create multiple deployments
    deployment_ids = []
    for i in range(3):
        deployment_id = await deployment.create_deployment(
            name=f"cluster-test-{i+1}",
            environment="production" if i % 2 == 0 else "staging",
            region="us-west-1",
            instance_type="t3.medium",
            min_instances=1,
            max_instances=5,
            desired_instances=2,
            port=8080 + i,
            domain=f"test{i+1}.aitbc.dev",
            database_config={"host": "localhost", "port": 5432, "name": f"aitbc_{i+1}"}
        )
        
        await deployment.deploy_application(deployment_id)
        deployment_ids.append(deployment_id)
    
    # Get cluster overview
    overview = await deployment.get_cluster_overview()
    
    assert overview is not None
    assert "total_deployments" in overview
    assert "running_deployments" in overview
    assert "total_instances" in overview
    assert "aggregate_metrics" in overview
    assert "recent_scaling_events" in overview
    assert "successful_scaling_rate" in overview
    assert "health_check_coverage" in overview
    
    # Check overview data
    assert overview["total_deployments"] == 3
    assert overview["running_deployments"] == 3
    assert overview["total_instances"] == 6  # 2 instances per deployment
    assert overview["health_check_coverage"] == 1.0  # 100% coverage
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra

def test_scaling_thresholds():
    """Test scaling threshold configuration"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Check default thresholds
    assert deployment.scaling_thresholds['cpu_high'] == 80.0
    assert deployment.scaling_thresholds['cpu_low'] == 20.0
    assert deployment.scaling_thresholds['memory_high'] == 85.0
    assert deployment.scaling_thresholds['memory_low'] == 30.0
    assert deployment.scaling_thresholds['error_rate_high'] == 5.0
    assert deployment.scaling_thresholds['response_time_high'] == 2000.0
    assert deployment.scaling_thresholds['min_uptime'] == 99.0

async def test_deployment_config_validation():
    """Test deployment configuration validation"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Test valid configuration
    deployment_id = await deployment.create_deployment(
        name="valid-config",
        environment="production",
        region="us-west-1",
        instance_type="t3.medium",
        min_instances=1,
        max_instances=10,
        desired_instances=5,
        port=8080,
        domain="valid.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc"}
    )
    
    assert deployment_id is not None
    
    config = deployment.deployments[deployment_id]
    assert config.min_instances <= config.desired_instances <= config.max_instances

async def test_metrics_initialization():
    """Test metrics initialization"""
    deployment = ProductionDeployment("/tmp/test_aitbc")
    
    # Create deployment
    deployment_id = await deployment.create_deployment(
        name="metrics-test",
        environment="production",
        region="us-west-1",
        instance_type="t3.medium",
        min_instances=1,
        max_instances=5,
        desired_instances=2,
        port=8080,
        domain="metrics.aitbc.dev",
        database_config={"host": "localhost", "port": 5432, "name": "aitbc"}
    )
    
    # Mock infrastructure deployment
    original_deploy_infra = deployment._deploy_infrastructure
    async def mock_deploy_infra(dep_config):
        return True
    deployment._deploy_infrastructure = mock_deploy_infra
    
    # Deploy to initialize metrics
    await deployment.deploy_application(deployment_id)
    
    # Check metrics were initialized
    metrics = deployment.metrics[deployment_id]
    assert metrics.deployment_id == deployment_id
    assert metrics.cpu_usage >= 0
    assert metrics.memory_usage >= 0
    assert metrics.disk_usage >= 0
    assert metrics.request_count >= 0
    assert metrics.error_rate >= 0
    assert metrics.response_time >= 0
    assert metrics.uptime_percentage >= 0
    assert metrics.active_instances >= 1
    
    # Restore original method
    deployment._deploy_infrastructure = original_deploy_infra

if __name__ == "__main__":
    # Run basic tests
    test_deployment_creation()
    test_scaling_thresholds()
    
    # Run async tests
    asyncio.run(test_create_deployment_config())
    asyncio.run(test_deployment_application())
    asyncio.run(test_manual_scaling())
    asyncio.run(test_auto_scaling())
    asyncio.run(test_deployment_status())
    asyncio.run(test_cluster_overview())
    asyncio.run(test_deployment_config_validation())
    asyncio.run(test_metrics_initialization())
    
    print("✅ All deployment tests passed!")
