"""
API Endpoint Tests
Tests for agent registration and discovery API endpoints
"""

import pytest
from app.models import AgentRegistrationRequest, AgentStatusUpdate


class TestAgentRegistrationRequest:
    """Test agent registration request model"""

    def test_registration_request_creation(self):  # noqa: F811
        """Test creating a registration request"""
        request = AgentRegistrationRequest(
            agent_id="agent_001",
            agent_type="worker",
            capabilities=["gpu", "cpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080"},
            metadata={"region": "us-east"},
        )

        assert request.agent_id == "agent_001"
        assert request.agent_type == "worker"
        assert len(request.capabilities) == 2
        assert len(request.services) == 1
        assert request.endpoints["http"] == "http://localhost:8080"
        assert request.metadata["region"] == "us-east"

    def test_registration_request_minimal(self):  # noqa: F811
        """Test registration request with minimal fields"""
        request = AgentRegistrationRequest(
            agent_id="agent_002",
            agent_type="specialist",
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8081"},
        )

        assert request.agent_id == "agent_002"
        assert request.agent_type == "specialist"
        assert request.metadata == {}


class TestAgentStatusUpdate:
    """Test agent status update model"""

    def test_status_update_creation(self):  # noqa: F811
        """Test creating a status update request"""
        request = AgentStatusUpdate(status="active", load_metrics={"cpu": 0.5, "memory": 0.6})

        assert request.status == "active"
        assert request.load_metrics["cpu"] == 0.5
        assert request.load_metrics["memory"] == 0.6

    def test_status_update_minimal(self):  # noqa: F811
        """Test status update with only status"""
        request = AgentStatusUpdate(status="busy")

        assert request.status == "busy"
        assert request.load_metrics == {}

    def test_status_update_status_values(self):  # noqa: F811
        """Test valid status values"""
        valid_statuses = ["active", "inactive", "busy", "maintenance", "error"]

        for status in valid_statuses:
            request = AgentStatusUpdate(status=status)
            assert request.status == status

    def test_status_update_complex_metrics(self):  # noqa: F811
        """Test status update with complex load metrics"""
        request = AgentStatusUpdate(
            status="active",
            load_metrics={
                "cpu": 0.7,
                "memory": 0.8,
                "disk": 0.3,
                "network_in": 1000,
                "network_out": 500,
                "active_connections": 50,
            },
        )

        assert len(request.load_metrics) == 6
        assert request.load_metrics["cpu"] == 0.7
        assert request.load_metrics["active_connections"] == 50

    def test_registration_request_with_all_fields(self):  # noqa: F811
        """Test agent registration with all optional fields"""
        request = AgentRegistrationRequest(
            agent_id="agent_004",
            agent_type="specialist",
            capabilities=["gpu", "storage"],
            services=["inference", "backup"],
            endpoints={"http": "http://localhost:8080", "grpc": "localhost:9090"},
            metadata={"region": "us-west", "gpu_model": "A100"},
        )

        assert request.agent_id == "agent_004"
        assert request.agent_type == "specialist"
        assert len(request.capabilities) == 2
        assert len(request.services) == 2
        assert len(request.endpoints) == 2
        assert request.metadata["gpu_model"] == "A100"

    def test_status_update_with_agent_id(self):  # noqa: F811
        """Test status update with detailed metrics"""
        request = AgentStatusUpdate(status="maintenance", load_metrics={"cpu": 0.1, "memory": 0.2, "gpu": 0.0})

        assert request.status == "maintenance"
        assert request.load_metrics["gpu"] == 0.0

    def test_registration_request_empty_capabilities(self):  # noqa: F811
        """Test registration request with empty capabilities"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_caps",
            agent_type="worker",
            capabilities=[],
            services=[],
            endpoints={"http": "http://localhost:8082"},
        )

        assert len(request.capabilities) == 0
        assert len(request.services) == 0

    def test_status_update_empty_metrics(self):  # noqa: F811
        """Test status update with empty load metrics"""
        request = AgentStatusUpdate(status="active", load_metrics={})

        assert request.load_metrics == {}
        assert request.status == "active"

    def test_registration_request_with_all_optional_fields(self):  # noqa: F811
        """Test registration request with all optional fields"""
        request = AgentRegistrationRequest(
            agent_id="agent_all_optional",
            agent_type="specialist",
            capabilities=["gpu", "storage"],
            services=["inference", "backup"],
            endpoints={"http": "http://localhost:8088", "grpc": "grpc://localhost:9094"},
            metadata={"region": "us-east", "zone": "us-east-1"},
        )

        assert len(request.capabilities) == 2
        assert len(request.services) == 2
        assert len(request.endpoints) == 2
        assert len(request.metadata) == 2

    def test_status_update_with_high_priority(self):  # noqa: F811
        """Test status update with high priority status"""
        request = AgentStatusUpdate(status="maintenance", load_metrics={"cpu": 0.0, "memory": 0.0})

        assert request.status == "maintenance"
        assert request.load_metrics["cpu"] == 0.0

    def test_registration_request_with_empty_services(self):  # noqa: F811
        """Test registration request with empty services list"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_services",
            agent_type="worker",
            capabilities=["storage"],
            services=[],
            endpoints={"http": "http://localhost:8100"},
        )

        assert len(request.services) == 0
        assert len(request.capabilities) == 1

    def test_status_update_with_empty_metrics(self):  # noqa: F811
        """Test status update with empty load metrics"""
        request = AgentStatusUpdate(status="idle", load_metrics={})

        assert len(request.load_metrics) == 0
        assert request.status == "idle"

    def test_registration_request_with_specialist_type(self):  # noqa: F811
        """Test registration request with specialist agent type"""
        request = AgentRegistrationRequest(
            agent_id="agent_specialist",
            agent_type="specialist",
            capabilities=["whisper", "transcription"],
            services=["audio_processing"],
            endpoints={"http": "http://localhost:8110"},
        )

        assert request.agent_type == "specialist"
        assert "whisper" in request.capabilities

    def test_status_update_with_degraded_status(self):  # noqa: F811
        """Test status update with degraded status"""
        request = AgentStatusUpdate(status="degraded", load_metrics={"cpu": 0.95, "memory": 0.90})

        assert request.status == "degraded"
        assert request.load_metrics["cpu"] == 0.95

    def test_registration_request_with_coordinator_type(self):  # noqa: F811
        """Test registration request with coordinator agent type"""
        request = AgentRegistrationRequest(
            agent_id="agent_coordinator",
            agent_type="coordinator",
            capabilities=["orchestration", "scheduling"],
            services=["workflow_management"],
            endpoints={"http": "http://localhost:8112"},
        )

        assert request.agent_type == "coordinator"
        assert "orchestration" in request.capabilities

    def test_status_update_with_offline_status(self):  # noqa: F811
        """Test status update with offline status"""
        request = AgentStatusUpdate(status="offline", load_metrics={})

        assert request.status == "offline"
        assert len(request.load_metrics) == 0

    def test_registration_request_with_multiple_services(self):  # noqa: F811
        """Test registration request with multiple services"""
        request = AgentRegistrationRequest(
            agent_id="agent_multi_services",
            agent_type="worker",
            capabilities=["gpu", "storage", "network"],
            services=["training", "inference", "backup"],
            endpoints={"http": "http://localhost:8115"},
        )

        assert len(request.services) == 3
        assert "training" in request.services

    def test_status_update_with_high_load_metrics(self):  # noqa: F811
        """Test status update with high load metrics"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.99, "memory": 0.95, "gpu": 1.0, "disk": 0.85})

        assert request.load_metrics["cpu"] == 0.99
        assert request.load_metrics["gpu"] == 1.0

    def test_registration_request_with_empty_capabilities(self):  # noqa: F811
        """Test registration request with empty capabilities"""
        request = AgentRegistrationRequest(
            agent_id="agent_no_caps",
            agent_type="worker",
            capabilities=[],
            services=["monitoring"],
            endpoints={"http": "http://localhost:8117"},
        )

        assert len(request.capabilities) == 0

    def test_status_update_with_single_metric(self):  # noqa: F811
        """Test status update with single load metric"""
        request = AgentStatusUpdate(status="active", load_metrics={"cpu": 0.5})

        assert len(request.load_metrics) == 1
        assert request.load_metrics["cpu"] == 0.5

    def test_registration_request_with_single_endpoint(self):  # noqa: F811
        """Test registration request with single endpoint"""
        request = AgentRegistrationRequest(
            agent_id="agent_single_endpoint",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8118"},
        )

        assert len(request.endpoints) == 1
        assert "http" in request.endpoints

    def test_status_update_with_empty_metrics(self):  # noqa: F811
        """Test status update with empty load metrics"""
        request = AgentStatusUpdate(status="idle", load_metrics={})

        assert len(request.load_metrics) == 0

    def test_registration_request_with_special_agent_id(self):  # noqa: F811
        """Test registration request with special characters in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent_special-123_test",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8119"},
        )

        assert "-" in request.agent_id
        assert "_" in request.agent_id

    def test_status_update_with_low_load_metrics(self):  # noqa: F811
        """Test status update with low load metrics"""
        request = AgentStatusUpdate(status="idle", load_metrics={"cpu": 0.01, "memory": 0.02, "gpu": 0.0, "disk": 0.1})

        assert request.load_metrics["cpu"] == 0.01
        assert request.load_metrics["gpu"] == 0.0

    def test_registration_request_with_numeric_agent_id(self):  # noqa: F811
        """Test registration request with numeric characters in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent_12345",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8120"},
        )

        assert "12345" in request.agent_id

    def test_status_update_with_status_maintenance(self):  # noqa: F811
        """Test status update with maintenance status"""
        request = AgentStatusUpdate(status="maintenance", load_metrics={"cpu": 0.0})

        assert request.status == "maintenance"

    def test_registration_request_with_multiple_endpoints(self):  # noqa: F811
        """Test registration request with multiple endpoints"""
        request = AgentRegistrationRequest(
            agent_id="agent_multi_endpoint",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8121", "grpc": "grpc://localhost:8122", "ws": "ws://localhost:8123"},
        )

        assert len(request.endpoints) == 3

    def test_status_update_with_high_load_metrics(self):  # noqa: F811
        """Test status update with high load metrics"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.95, "memory": 0.98, "gpu": 0.99, "disk": 0.90})

        assert request.load_metrics["cpu"] == 0.95
        assert request.load_metrics["gpu"] == 0.99

    def test_registration_request_with_empty_capabilities(self):  # noqa: F811
        """Test registration request with empty capabilities"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_caps",
            agent_type="worker",
            capabilities=[],
            services=["inference"],
            endpoints={"http": "http://localhost:8124"},
        )

        assert len(request.capabilities) == 0

    def test_status_update_with_single_metric(self):  # noqa: F811
        """Test status update with single load metric"""
        request = AgentStatusUpdate(status="idle", load_metrics={"cpu": 0.5})

        assert len(request.load_metrics) == 1
        assert "cpu" in request.load_metrics

    def test_registration_request_with_single_capability(self):  # noqa: F811
        """Test registration request with single capability"""
        request = AgentRegistrationRequest(
            agent_id="agent_single_cap",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8125"},
        )

        assert len(request.capabilities) == 1

    def test_status_update_with_status_busy(self):  # noqa: F811
        """Test status update with busy status"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.8})

        assert request.status == "busy"

    def test_registration_request_with_single_endpoint(self):  # noqa: F811
        """Test registration request with single endpoint"""
        request = AgentRegistrationRequest(
            agent_id="agent_single_endpoint",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8126"},
        )

        assert len(request.endpoints) == 1

    def test_status_update_with_zero_load_metrics(self):  # noqa: F811
        """Test status update with zero load metrics"""
        request = AgentStatusUpdate(status="idle", load_metrics={"cpu": 0.0, "memory": 0.0})

        assert request.load_metrics["cpu"] == 0.0
        assert request.load_metrics["memory"] == 0.0

    def test_registration_request_with_multiple_endpoints(self):  # noqa: F811
        """Test registration request with multiple endpoints"""
        request = AgentRegistrationRequest(
            agent_id="agent_multi_endpoint",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8127", "grpc": "localhost:8128"},
        )

        assert len(request.endpoints) == 2

    def test_status_update_with_high_priority_status(self):  # noqa: F811
        """Test status update with high priority status"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.95, "memory": 0.9})

        assert request.load_metrics["cpu"] > 0.9
        assert request.load_metrics["memory"] > 0.8

    def test_registration_request_with_multiple_capabilities(self):  # noqa: F811
        """Test registration request with multiple capabilities"""
        request = AgentRegistrationRequest(
            agent_id="agent_multi_caps",
            agent_type="worker",
            capabilities=["gpu", "cpu", "storage"],
            services=["inference"],
            endpoints={"http": "http://localhost:8129"},
        )

        assert len(request.capabilities) == 3

    def test_status_update_with_single_load_metric(self):  # noqa: F811
        """Test status update with single load metric"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.8})

        assert len(request.load_metrics) == 1

    def test_registration_request_with_empty_agent_type(self):  # noqa: F811
        """Test registration request with empty agent_type (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_type",
            agent_type="",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8130"},
        )

        assert request.agent_type == ""

    def test_status_update_with_empty_status(self):  # noqa: F811
        """Test status update with empty status (edge case)"""
        request = AgentStatusUpdate(status="", load_metrics={"cpu": 0.5})

        assert request.status == ""

    def test_registration_request_with_multiple_services(self):  # noqa: F811
        """Test registration request with multiple services"""
        request = AgentRegistrationRequest(
            agent_id="agent_multi_services",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference", "training", "storage"],
            endpoints={"http": "http://localhost:8131"},
        )

        assert len(request.services) == 3

    def test_status_update_with_multiple_load_metrics(self):  # noqa: F811
        """Test status update with multiple load metrics"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.8, "memory": 0.7, "gpu": 0.6})

        assert len(request.load_metrics) == 3

    def test_registration_request_with_empty_endpoints(self):  # noqa: F811
        """Test registration request with empty endpoints (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_endpoints", agent_type="worker", capabilities=["gpu"], services=["inference"], endpoints={}
        )

        assert len(request.endpoints) == 0

    def test_status_update_with_empty_load_metrics(self):  # noqa: F811
        """Test status update with empty load metrics (edge case)"""
        request = AgentStatusUpdate(status="busy", load_metrics={})

        assert len(request.load_metrics) == 0

    def test_registration_request_with_empty_capabilities(self):  # noqa: F811
        """Test registration request with empty capabilities (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_caps",
            agent_type="worker",
            capabilities=[],
            services=["inference"],
            endpoints={"http": "http://localhost:8132"},
        )

        assert len(request.capabilities) == 0

    def test_status_update_with_zero_load_metric(self):  # noqa: F811
        """Test status update with zero load metric (edge case)"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": 0.0})

        assert request.load_metrics["cpu"] == 0.0

    def test_registration_request_with_empty_services(self):  # noqa: F811
        """Test registration request with empty services (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_services",
            agent_type="worker",
            capabilities=["gpu"],
            services=[],
            endpoints={"http": "http://localhost:8133"},
        )

        assert len(request.services) == 0

    def test_status_update_with_negative_load_metric(self):  # noqa: F811
        """Test status update with negative load metric (edge case)"""
        request = AgentStatusUpdate(status="busy", load_metrics={"cpu": -0.1})

        assert request.load_metrics["cpu"] == -0.1

    def test_registration_request_with_numeric_agent_id(self):  # noqa: F811
        """Test registration request with numeric characters in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8134"},
        )

        assert "123" in request.agent_id

    def test_status_update_with_mixed_case_status(self):  # noqa: F811
        """Test status update with mixed case status"""
        request = AgentStatusUpdate(status="Busy", load_metrics={"cpu": 0.5})

        assert request.status == "Busy"

    def test_registration_request_with_mixed_case_agent_type(self):  # noqa: F811
        """Test registration request with mixed case agent_type"""
        request = AgentRegistrationRequest(
            agent_id="agent_mixed_type",
            agent_type="Worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8135"},
        )

        assert request.agent_type == "Worker"

    def test_status_update_with_numeric_status(self):  # noqa: F811
        """Test status update with numeric characters in status"""
        request = AgentStatusUpdate(status="status123", load_metrics={"cpu": 0.5})

        assert "123" in request.status

    def test_registration_request_with_empty_agent_id(self):  # noqa: F811
        """Test registration request with empty agent_id (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8136"},
        )

        assert request.agent_id == ""

    def test_status_update_with_empty_status(self):  # noqa: F811
        """Test status update with empty status (edge case)"""
        request = AgentStatusUpdate(status="", load_metrics={"cpu": 0.5})

        assert request.status == ""

    def test_registration_request_with_single_character_agent_id(self):  # noqa: F811
        """Test registration request with single character agent_id"""
        request = AgentRegistrationRequest(
            agent_id="A",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8137"},
        )

        assert len(request.agent_id) == 1

    def test_status_update_with_single_character_status(self):  # noqa: F811
        """Test status update with single character status"""
        request = AgentStatusUpdate(status="B", load_metrics={"cpu": 0.5})

        assert len(request.status) == 1

    def test_registration_request_with_numeric_agent_id(self):  # noqa: F811
        """Test registration request with numeric agent_id (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8138"},
        )

        assert request.agent_id == "123"

    def test_status_update_with_numeric_status(self):  # noqa: F811
        """Test status update with numeric status (edge case)"""
        request = AgentStatusUpdate(status="123", load_metrics={"cpu": 0.5})

        assert request.status == "123"

    def test_registration_request_with_special_characters_agent_id(self):  # noqa: F811
        """Test registration request with special characters in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent@#$",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8139"},
        )

        assert "@" in request.agent_id
        assert "#" in request.agent_id
        assert "$" in request.agent_id

    def test_status_update_with_special_characters_status(self):  # noqa: F811
        """Test status update with special characters in status"""
        request = AgentStatusUpdate(status="status@#$", load_metrics={"cpu": 0.5})

        assert "@" in request.status
        assert "#" in request.status
        assert "$" in request.status

    def test_registration_request_with_spaces_agent_id(self):  # noqa: F811
        """Test registration request with spaces in agent_id (edge case)"""
        request = AgentRegistrationRequest(
            agent_id="agent 123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8140"},
        )

        assert " " in request.agent_id

    def test_status_update_with_spaces_status(self):  # noqa: F811
        """Test status update with spaces in status (edge case)"""
        request = AgentStatusUpdate(status="status 123", load_metrics={"cpu": 0.5})

        assert " " in request.status

    def test_registration_request_with_underscore_agent_id(self):  # noqa: F811
        """Test registration request with underscore in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent_123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8141"},
        )

        assert "_" in request.agent_id

    def test_status_update_with_underscore_status(self):  # noqa: F811
        """Test status update with underscore in status"""
        request = AgentStatusUpdate(status="status_123", load_metrics={"cpu": 0.5})

        assert "_" in request.status

    def test_registration_request_with_colon_agent_id(self):  # noqa: F811
        """Test registration request with colon in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent:123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8142"},
        )

        assert ":" in request.agent_id

    def test_status_update_with_colon_status(self):  # noqa: F811
        """Test status update with colon in status"""
        request = AgentStatusUpdate(status="status:123", load_metrics={"cpu": 0.5})

        assert ":" in request.status

    def test_registration_request_with_equals_agent_id(self):  # noqa: F811
        """Test registration request with equals in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent=123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8143"},
        )

        assert "=" in request.agent_id

    def test_status_update_with_equals_status(self):  # noqa: F811
        """Test status update with equals in status"""
        request = AgentStatusUpdate(status="status=123", load_metrics={"cpu": 0.5})

        assert "=" in request.status

    def test_registration_request_with_bracket_agent_id(self):  # noqa: F811
        """Test registration request with bracket in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent[123]",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8144"},
        )

        assert "[" in request.agent_id
        assert "]" in request.agent_id

    def test_status_update_with_bracket_status(self):  # noqa: F811
        """Test status update with bracket in status"""
        request = AgentStatusUpdate(status="status[123]", load_metrics={"cpu": 0.5})

        assert "[" in request.status
        assert "]" in request.status

    def test_registration_request_with_curly_bracket_agent_id(self):  # noqa: F811
        """Test registration request with curly bracket in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent{123}",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8145"},
        )

        assert "{" in request.agent_id
        assert "}" in request.agent_id

    def test_status_update_with_curly_bracket_status(self):  # noqa: F811
        """Test status update with curly bracket in status"""
        request = AgentStatusUpdate(status="status{123}", load_metrics={"cpu": 0.5})

        assert "{" in request.status
        assert "}" in request.status

    def test_registration_request_with_dollar_agent_id(self):  # noqa: F811
        """Test registration request with dollar in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent$123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8146"},
        )

        assert "$" in request.agent_id

    def test_status_update_with_dollar_status(self):  # noqa: F811
        """Test status update with dollar in status"""
        request = AgentStatusUpdate(status="status$123", load_metrics={"cpu": 0.5})

        assert "$" in request.status

    def test_status_update_with_hash_status(self):  # noqa: F811
        """Test status update with hash in status"""
        request = AgentStatusUpdate(status="status#123", load_metrics={"cpu": 0.5})

        assert "#" in request.status

    def test_status_update_with_exclamation_status(self):  # noqa: F811
        """Test status update with exclamation in status"""
        request = AgentStatusUpdate(status="status!123", load_metrics={"cpu": 0.5})

        assert "!" in request.status

    def test_registration_request_with_asterisk_agent_id(self):  # noqa: F811
        """Test registration request with asterisk in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent*123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8161"},
        )

        assert "*" in request.agent_id

    def test_status_update_with_asterisk_status(self):  # noqa: F811
        """Test status update with asterisk in status"""
        request = AgentStatusUpdate(status="status*123", load_metrics={"cpu": 0.5})

        assert "*" in request.status

    def test_registration_request_with_equals_agent_id(self):  # noqa: F811
        """Test registration request with equals in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent=123",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8162"},
        )

        assert "=" in request.agent_id

    def test_status_update_with_equals_status(self):  # noqa: F811
        """Test status update with equals in status"""
        request = AgentStatusUpdate(status="status=123", load_metrics={"cpu": 0.5})

        assert "=" in request.status

    def test_registration_request_with_curly_brace_agent_id(self):  # noqa: F811
        """Test registration request with curly brace in agent_id"""
        request = AgentRegistrationRequest(
            agent_id="agent{123}",
            agent_type="worker",
            capabilities=["gpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8163"},
        )

        assert "{" in request.agent_id

    def test_status_update_with_curly_brace_status(self):  # noqa: F811
        """Test status update with curly brace in status"""
        request = AgentStatusUpdate(status="status{123}", load_metrics={"cpu": 0.5})

        assert "{" in request.status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
