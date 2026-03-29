"""Test suite for AITBC Agent SDK"""

import pytest
from aitbc_agent.agent import AITBCAgent, Agent, AgentCapabilities, AgentIdentity


class TestAITBCAgent:
    """Test AITBC Agent high-level wrapper"""

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
            "capabilities": ["inference", "training"],
        }
        agent = AITBCAgent(**config)
        assert agent.compute_type == "gpu"
        assert "inference" in agent.capabilities


class TestAgentCore:
    """Test core Agent class"""

    def test_create_agent(self):
        """Test Agent.create factory"""
        agent = Agent.create(
            name="provider-1",
            agent_type="compute_provider",
            capabilities={"compute_type": "inference"},
        )
        assert agent.identity.name == "provider-1"
        assert agent.capabilities.compute_type == "inference"
        assert agent.registered is False

    def test_agent_to_dict(self):
        """Test agent serialisation round-trip"""
        agent = Agent.create(
            name="worker",
            agent_type="general",
            capabilities={"compute_type": "processing"},
        )
        d = agent.to_dict()
        assert "id" in d
        assert d["capabilities"]["compute_type"] == "processing"

    def test_capabilities_defaults(self):
        """Test AgentCapabilities default values"""
        caps = AgentCapabilities(compute_type="inference")
        assert caps.supported_models == []
        assert caps.max_concurrent_jobs == 1
        assert caps.gpu_memory is None


class TestImports:
    """Verify public API surface"""

    def test_all_exports(self):
        import aitbc_agent
        for name in (
            "Agent", "AITBCAgent", "ComputeProvider",
            "ComputeConsumer", "PlatformBuilder", "SwarmCoordinator",
        ):
            assert hasattr(aitbc_agent, name), f"Missing export: {name}"


if __name__ == "__main__":
    pytest.main([__file__])
