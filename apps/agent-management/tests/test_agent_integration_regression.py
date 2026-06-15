"""
Regression tests for agent_integration.py
These tests capture current behavior before extracting shared logic.
"""

from unittest.mock import Mock

import pytest
from app.services.agent_integration import (
    AgentDeploymentConfig,
    DeploymentStatus,
    ZKProofService,
)


@pytest.mark.unit
class TestDeploymentStatus:
    """Test DeploymentStatus enum"""

    def test_deployment_status_values(self):
        """Test that all expected status values exist"""
        assert DeploymentStatus.PENDING == "pending"
        assert DeploymentStatus.DEPLOYING == "deploying"
        assert DeploymentStatus.DEPLOYED == "deployed"
        assert DeploymentStatus.FAILED == "failed"
        assert DeploymentStatus.RETRYING == "retrying"
        assert DeploymentStatus.TERMINATED == "terminated"


@pytest.mark.unit
class TestAgentDeploymentConfig:
    """Test AgentDeploymentConfig model"""

    def test_default_values(self):
        """Test default configuration values"""
        config = AgentDeploymentConfig(workflow_id="test_workflow", deployment_name="test_deployment")

        assert config.id.startswith("deploy_")
        assert config.workflow_id == "test_workflow"
        assert config.deployment_name == "test_deployment"
        assert config.version == "1.0.0"
        assert config.min_cpu_cores == 1.0
        assert config.min_memory_mb == 1024
        assert config.min_storage_gb == 10
        assert config.requires_gpu is False
        assert config.gpu_memory_mb is None
        assert config.min_instances == 1
        assert config.max_instances == 5
        assert config.auto_scaling is True
        assert config.health_check_endpoint == "/health"
        assert config.health_check_interval == 30
        assert config.health_check_timeout == 10
        assert config.max_failures == 3
        assert config.rollout_strategy == "rolling"
        assert config.rollback_enabled is True
        assert config.deployment_timeout == 1800

    def test_custom_values(self):
        """Test custom configuration values"""
        config = AgentDeploymentConfig(
            workflow_id="custom_workflow",
            deployment_name="custom_deployment",
            version="2.0.0",
            min_cpu_cores=4.0,
            min_memory_mb=8192,
            requires_gpu=True,
            gpu_memory_mb=16384,
            min_instances=2,
            max_instances=10,
            auto_scaling=False,
            rollout_strategy="blue-green",
        )

        assert config.version == "2.0.0"
        assert config.min_cpu_cores == 4.0
        assert config.min_memory_mb == 8192
        assert config.requires_gpu is True
        assert config.gpu_memory_mb == 16384
        assert config.min_instances == 2
        assert config.max_instances == 10
        assert config.auto_scaling is False
        assert config.rollout_strategy == "blue-green"


@pytest.mark.unit
class TestZKProofService:
    """Test ZKProofService mock"""

    @pytest.mark.asyncio
    async def test_generate_zk_proof(self):
        """Test ZK proof generation"""
        mock_session = Mock()
        service = ZKProofService(mock_session)

        result = await service.generate_zk_proof("test_circuit", {"input": "value"})

        assert "proof_id" in result
        assert result["circuit_name"] == "test_circuit"
        assert result["inputs"] == {"input": "value"}
        assert result["proof_size"] == 1024
        assert result["generation_time"] == 0.1

    @pytest.mark.asyncio
    async def test_verify_proof(self):
        """Test ZK proof verification"""
        mock_session = Mock()
        service = ZKProofService(mock_session)

        result = await service.verify_proof("test_proof_id")

        assert result["verified"] is True
        assert result["verification_time"] == 0.05
        assert "details" in result
