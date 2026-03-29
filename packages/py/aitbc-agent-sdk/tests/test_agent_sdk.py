"""Test suite for AITBC Agent SDK"""

import pytest
from aitbc_agent.agent import AITBCAgent
from aitbc_agent.compute_provider import ComputeProvider
from aitbc_agent.swarm_coordinator import SwarmCoordinator


class TestAITBCAgent:
    """Test AITBC Agent functionality"""
    
    def test_agent_initialization(self):
        """Test agent can be initialized"""
        agent = AITBCAgent(agent_id="test-agent")
        assert agent.agent_id == "test-agent"
        assert agent.status == "initialized"
    
    def test_agent_config_validation(self):
        """Test agent configuration validation"""
        config = {
            "agent_id": "test-agent",
            "compute_type": "gpu",
            "capabilities": ["inference", "training"]
        }
        agent = AITBCAgent(**config)
        assert agent.compute_type == "gpu"
        assert "inference" in agent.capabilities


class TestComputeProvider:
    """Test Compute Provider functionality"""
    
    def test_provider_registration(self):
        """Test provider can register with network"""
        provider = ComputeProvider(
            provider_id="test-provider",
            gpu_count=4,
            memory_gb=32
        )
        assert provider.provider_id == "test-provider"
        assert provider.gpu_count == 4
        assert provider.memory_gb == 32
    
    def test_resource_availability(self):
        """Test resource availability reporting"""
        provider = ComputeProvider(
            provider_id="test-provider",
            gpu_count=2,
            memory_gb=16
        )
        resources = provider.get_available_resources()
        assert resources["gpu_count"] == 2
        assert resources["memory_gb"] == 16


class TestSwarmCoordinator:
    """Test Swarm Coordinator functionality"""
    
    def test_coordinator_initialization(self):
        """Test coordinator initialization"""
        coordinator = SwarmCoordinator(coordinator_id="test-coordinator")
        assert coordinator.coordinator_id == "test-coordinator"
        assert len(coordinator.agents) == 0
    
    def test_agent_registration(self):
        """Test agent registration with coordinator"""
        coordinator = SwarmCoordinator(coordinator_id="test-coordinator")
        agent = AITBCAgent(agent_id="test-agent")
        
        success = coordinator.register_agent(agent)
        assert success is True
        assert len(coordinator.agents) == 1
        assert "test-agent" in coordinator.agents


if __name__ == "__main__":
    pytest.main([__file__])
