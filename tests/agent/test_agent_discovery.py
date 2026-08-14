"""
Agent Discovery Tests
Tests for agent registration, discovery, capability matching, and agent registry
"""

from datetime import UTC, datetime

import pytest
from agent_app.routing.agent_discovery import (
    AgentInfo,
    AgentStatus,
    AgentType,
    create_agent_info,
)


class TestAgentInfo:
    """Test agent information structure"""

    def test_agent_info_creation(self):  # noqa: F811
        """Test creating agent information"""
        agent_info = AgentInfo(
            agent_id="agent_001",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080"},
            metadata={"region": "us-east"},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
            health_score=0.95,
        )

        assert agent_info.agent_id == "agent_001"
        assert agent_info.agent_type == AgentType.WORKER
        assert agent_info.status == AgentStatus.ACTIVE
        assert len(agent_info.capabilities) == 2
        assert agent_info.health_score == 0.95

    def test_agent_info_serialization(self):  # noqa: F811
        """Test agent info to_dict and from_dict"""
        agent_info = AgentInfo(
            agent_id="agent_002",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8081"},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        )

        # Convert to dict
        agent_dict = agent_info.to_dict()
        assert "agent_id" in agent_dict
        assert "agent_type" in agent_dict
        assert "capabilities" in agent_dict
        assert "health_score" in agent_dict

        # Convert from dict
        restored_info = AgentInfo.from_dict(agent_dict)
        assert restored_info.agent_id == agent_info.agent_id
        assert restored_info.agent_type == agent_info.agent_type
        assert restored_info.status == agent_info.status

    def test_create_agent_info_factory(self):  # noqa: F811
        """Test factory function for creating agent info"""
        agent_info = create_agent_info(
            agent_id="agent_003",
            agent_type="worker",
            capabilities=["compute"],
            services=["processing"],
            endpoints={"http": "http://localhost:8082"},
        )

        assert agent_info.agent_id == "agent_003"
        assert agent_info.agent_type == AgentType.WORKER
        assert agent_info.status == AgentStatus.ACTIVE
        assert len(agent_info.capabilities) == 1


class TestAgentRegistry:
    """Test agent registry functionality"""


class TestAgentDiscoveryService:
    """Test agent discovery service"""

    def test_agent_info_empty_capabilities(self):  # noqa: F811
        """Test agent info with empty capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_caps",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 0
        assert len(agent.services) == 0

    def test_agent_info_multiple_endpoints(self):  # noqa: F811
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080", "grpc": "grpc://localhost:9090", "ws": "ws://localhost:8081"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 3
        assert "http" in agent.endpoints
        assert "grpc" in agent.endpoints
        assert "ws" in agent.endpoints

    def test_agent_info_with_multiple_capabilities(self):  # noqa: F811
        """Test agent info with multiple capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_caps",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "storage", "network", "compute"],
            services=["inference", "backup", "routing", "training"],
            endpoints={"http": "http://localhost:8086"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 4
        assert len(agent.services) == 4
        assert "gpu" in agent.capabilities
        assert "training" in agent.services

    def test_agent_info_metadata_manipulation(self):  # noqa: F811
        """Test agent info metadata manipulation"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8087"},
            metadata={"region": "us-west"},
            last_heartbeat=now,
            registration_time=now,
        )

        # Add metadata
        agent.metadata["gpu_model"] = "A100"
        agent.metadata["zone"] = "us-west-1"

        assert len(agent.metadata) == 3
        assert "gpu_model" in agent.metadata
        assert agent.metadata["region"] == "us-west"

    def test_agent_info_with_specialist_type(self):  # noqa: F811
        """Test agent info with specialist agent type"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_specialist",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["whisper", "transcription"],
            services=["audio_processing"],
            endpoints={"http": "http://localhost:8101"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_type == AgentType.SPECIALIST
        assert "whisper" in agent.capabilities

    def test_agent_info_with_coordinator_type(self):  # noqa: F811
        """Test agent info with coordinator agent type"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_coordinator",
            agent_type=AgentType.COORDINATOR,
            status=AgentStatus.ACTIVE,
            capabilities=["orchestration", "scheduling"],
            services=["workflow_management"],
            endpoints={"http": "http://localhost:8102"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_type == AgentType.COORDINATOR
        assert "orchestration" in agent.capabilities

    def test_agent_info_with_multiple_capabilities(self):  # noqa: F811
        """Test agent info with multiple capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_cap",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "storage", "network"],
            services=["training", "inference"],
            endpoints={"http": "http://localhost:8113"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 3
        assert "gpu" in agent.capabilities
        assert "storage" in agent.capabilities

    def test_agent_info_with_single_service(self):  # noqa: F811
        """Test agent info with single service"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_service",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["transcription"],
            services=["audio"],
            endpoints={"http": "http://localhost:8114"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 1
        assert agent.services[0] == "audio"

    def test_agent_info_with_empty_endpoints(self):  # noqa: F811
        """Test agent info with empty endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_no_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            services=["training"],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 0

    def test_agent_info_with_multiple_endpoints(self):  # noqa: F811
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8116", "grpc": "grpc://localhost:9096", "ws": "ws://localhost:8096"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 3
        assert "http" in agent.endpoints
        assert "grpc" in agent.endpoints

    def test_agent_info_with_no_services(self):  # noqa: F811
        """Test agent info with no services"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_no_services",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            services=[],
            endpoints={"http": "http://localhost:8117"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 0

    def test_agent_info_with_single_capability(self):  # noqa: F811
        """Test agent info with single capability"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_cap",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["transcription"],
            services=["audio"],
            endpoints={"http": "http://localhost:8118"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 1
        assert agent.capabilities[0] == "transcription"

    def test_agent_info_with_specialist_type(self):  # noqa: F811
        """Test agent info with specialist agent type"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_specialist",
            agent_type=AgentType.SPECIALIST,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu", "cuda"],
            services=["training"],
            endpoints={"http": "http://localhost:8119"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_type == AgentType.SPECIALIST

    def test_agent_info_with_maintenance_status(self):  # noqa: F811
        """Test agent info with maintenance status"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_maintenance",
            agent_type=AgentType.WORKER,
            status=AgentStatus.MAINTENANCE,
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8120"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.status == AgentStatus.MAINTENANCE

    def test_agent_info_with_numeric_agent_id(self):  # noqa: F811
        """Test agent info with numeric characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_12345",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8121"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "12345" in agent.agent_id

    def test_agent_info_with_long_name_in_metadata(self):  # noqa: F811
        """Test agent info with long name in metadata"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_long_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8122"},
            metadata={"name": "A very long agent name for testing purposes"},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata["name"]) > 20

    def test_agent_info_with_empty_metadata(self):  # noqa: F811
        """Test agent info with empty metadata"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8123"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 0

    def test_agent_info_with_multiple_metadata_fields(self):  # noqa: F811
        """Test agent info with multiple metadata fields"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_metadata",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8124"},
            metadata={"name": "Agent", "version": "1.0", "region": "us-west"},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 3

    def test_agent_info_with_single_capability(self):  # noqa: F811
        """Test agent info with single capability"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_cap",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8125"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 1

    def test_agent_info_with_multiple_services(self):  # noqa: F811
        """Test agent info with multiple services"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_services",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference", "training", "storage"],
            endpoints={"http": "http://localhost:8126"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 3

    def test_agent_info_with_empty_endpoints(self):  # noqa: F811
        """Test agent info with empty endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_endpoints",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 0

    def test_agent_info_with_single_endpoint(self):  # noqa: F811
        """Test agent info with single endpoint"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_endpoint",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8127"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 1

    def test_agent_info_with_special_characters_in_agent_id(self):  # noqa: F811
        """Test agent info with special characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent-123_special@",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8128"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "-" in agent.agent_id
        assert "@" in agent.agent_id

    def test_agent_info_with_underscore_in_agent_id(self):  # noqa: F811
        """Test agent info with underscore in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_123_456",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8129"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "_" in agent.agent_id

    def test_agent_info_with_mixed_case_agent_id(self):  # noqa: F811
        """Test agent info with mixed case agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="Agent123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8130"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_id[0].isupper()

    def test_agent_info_with_single_service(self):  # noqa: F811
        """Test agent info with single service"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_service",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8131"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 1

    def test_agent_info_with_empty_capabilities(self):  # noqa: F811
        """Test agent info with empty capabilities"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_caps",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=["inference"],
            endpoints={"http": "http://localhost:8132"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 0

    def test_agent_info_with_multiple_metadata_keys(self):  # noqa: F811
        """Test agent info with multiple metadata keys"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_meta",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8133"},
            metadata={"key1": "value1", "key2": "value2", "key3": "value3"},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 3

    def test_agent_info_with_empty_metadata(self):  # noqa: F811
        """Test agent info with empty metadata"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_empty_meta_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8134"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.metadata) == 0

    def test_agent_info_with_multiple_endpoints(self):  # noqa: F811
        """Test agent info with multiple endpoints"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_multi_endpoints_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8135", "grpc": "localhost:8136"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.endpoints) == 2

    def test_agent_info_with_single_capability(self):  # noqa: F811
        """Test agent info with single capability"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_cap_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8137"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.capabilities) == 1

    def test_agent_info_with_single_service(self):  # noqa: F811
        """Test agent info with single service"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_single_service_discovery",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8138"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.services) == 1

    def test_agent_info_with_numeric_agent_id(self):  # noqa: F811
        """Test agent info with numeric characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8139"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "123" in agent.agent_id

    def test_agent_info_with_hyphen_in_agent_id(self):  # noqa: F811
        """Test agent info with hyphen in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent-123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8140"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "-" in agent.agent_id

    def test_agent_info_with_special_characters_in_agent_id(self):  # noqa: F811
        """Test agent info with special characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent@#$",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8141"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "@" in agent.agent_id
        assert "#" in agent.agent_id
        assert "$" in agent.agent_id

    def test_agent_info_with_underscore_in_agent_id(self):  # noqa: F811
        """Test agent info with underscore in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8142"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "_" in agent.agent_id

    def test_agent_info_with_empty_agent_id(self):  # noqa: F811
        """Test agent info with empty agent_id (edge case)"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8143"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_id == ""

    def test_agent_info_with_single_character_agent_id(self):  # noqa: F811
        """Test agent info with single character agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="A",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8144"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert len(agent.agent_id) == 1

    def test_agent_info_with_mixed_case_agent_id(self):  # noqa: F811
        """Test agent info with mixed case agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="AgentID",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8145"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "Agent" in agent.agent_id
        assert "ID" in agent.agent_id

    def test_agent_info_with_numeric_agent_id(self):  # noqa: F811
        """Test agent info with numeric agent_id (edge case)"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8146"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert agent.agent_id == "123"

    def test_agent_info_with_hyphen_in_agent_id(self):  # noqa: F811
        """Test agent info with hyphen in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent-123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8147"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "-" in agent.agent_id

    def test_agent_info_with_dot_in_agent_id(self):  # noqa: F811
        """Test agent info with dot in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent.123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8148"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "." in agent.agent_id

    def test_agent_info_with_special_characters_in_agent_id(self):  # noqa: F811
        """Test agent info with various special characters in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent@#$",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8149"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "@" in agent.agent_id
        assert "#" in agent.agent_id
        assert "$" in agent.agent_id

    def test_agent_info_with_spaces_in_agent_id(self):  # noqa: F811
        """Test agent info with spaces in agent_id (edge case)"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent 123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8150"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert " " in agent.agent_id

    def test_agent_info_with_underscore_in_agent_id(self):  # noqa: F811
        """Test agent info with underscore in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent_123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8151"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "_" in agent.agent_id

    def test_agent_info_with_pipe_in_agent_id(self):  # noqa: F811
        """Test agent info with pipe in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent|123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8152"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "|" in agent.agent_id

    def test_agent_info_with_colon_in_agent_id(self):  # noqa: F811
        """Test agent info with colon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent:123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8153"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ":" in agent.agent_id

    def test_agent_info_with_semicolon_in_agent_id(self):  # noqa: F811
        """Test agent info with semicolon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent;123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8154"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ";" in agent.agent_id

    def test_agent_info_with_equals_in_agent_id(self):  # noqa: F811
        """Test agent info with equals in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent=123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8155"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "=" in agent.agent_id

    def test_agent_info_with_plus_in_agent_id(self):  # noqa: F811
        """Test agent info with plus in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent+123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8156"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "+" in agent.agent_id

    def test_agent_info_with_slash_in_agent_id(self):  # noqa: F811
        """Test agent info with slash in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent/123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8157"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "/" in agent.agent_id

    def test_agent_info_with_backslash_in_agent_id(self):  # noqa: F811
        """Test agent info with backslash in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent\\123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8158"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "\\" in agent.agent_id

    def test_agent_info_with_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent[123]",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8159"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "[" in agent.agent_id
        assert "]" in agent.agent_id

    def test_agent_info_with_parenthesis_in_agent_id(self):  # noqa: F811
        """Test agent info with parenthesis in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent(123)",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8160"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "(" in agent.agent_id
        assert ")" in agent.agent_id

    def test_agent_info_with_curly_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with curly bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent{123}",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8161"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "{" in agent.agent_id
        assert "}" in agent.agent_id

    def test_agent_info_with_angle_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with angle bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent<123>",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8162"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "<" in agent.agent_id
        assert ">" in agent.agent_id

    def test_agent_info_with_dollar_in_agent_id(self):  # noqa: F811
        """Test agent info with dollar in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent$123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8163"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "$" in agent.agent_id

    def test_agent_info_with_at_in_agent_id(self):  # noqa: F811
        """Test agent info with at in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent@123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8164"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "@" in agent.agent_id

    def test_agent_info_with_percent_in_agent_id(self):  # noqa: F811
        """Test agent info with percent in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent%123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8165"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "%" in agent.agent_id

    def test_agent_info_with_ampersand_in_agent_id(self):  # noqa: F811
        """Test agent info with ampersand in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent&123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8166"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "&" in agent.agent_id

    def test_agent_info_with_hash_in_agent_id(self):  # noqa: F811
        """Test agent info with hash in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent#123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8167"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "#" in agent.agent_id

    def test_agent_info_with_exclamation_in_agent_id(self):  # noqa: F811
        """Test agent info with exclamation in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent!123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8168"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "!" in agent.agent_id

    def test_agent_info_with_asterisk_in_agent_id(self):  # noqa: F811
        """Test agent info with asterisk in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent*123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8169"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "*" in agent.agent_id

    def test_agent_info_with_plus_in_agent_id(self):  # noqa: F811
        """Test agent info with plus in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent+123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8170"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "+" in agent.agent_id

    def test_agent_info_with_equals_in_agent_id(self):  # noqa: F811
        """Test agent info with equals in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent=123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8171"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "=" in agent.agent_id

    def test_agent_info_with_bracket_in_agent_id(self):  # noqa: F811
        """Test agent info with bracket in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent[123]",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8172"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "[" in agent.agent_id

    def test_agent_info_with_curly_brace_in_agent_id(self):  # noqa: F811
        """Test agent info with curly brace in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent{123}",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8173"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "{" in agent.agent_id

    def test_agent_info_with_pipe_in_agent_id(self):  # noqa: F811
        """Test agent info with pipe in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent|123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8174"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "|" in agent.agent_id

    def test_agent_info_with_colon_in_agent_id(self):  # noqa: F811
        """Test agent info with colon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent:123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8175"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ":" in agent.agent_id

    def test_agent_info_with_semicolon_in_agent_id(self):  # noqa: F811
        """Test agent info with semicolon in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent;123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8176"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert ";" in agent.agent_id

    def test_agent_info_with_comma_in_agent_id(self):  # noqa: F811
        """Test agent info with comma in agent_id"""
        now = datetime.now(UTC)
        agent = AgentInfo(
            agent_id="agent,123",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8177"},
            metadata={},
            last_heartbeat=now,
            registration_time=now,
        )

        assert "," in agent.agent_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
