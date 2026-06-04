"""
API Endpoint Tests
Tests for agent registration and discovery API endpoints
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest

from app.models import AgentRegistrationRequest, AgentStatusUpdate


class TestAgentRegistrationRequest:
    """Test agent registration request model"""

    def test_registration_request_creation(self):
        """Test creating a registration request"""
        request = AgentRegistrationRequest(
            agent_id="agent_001",
            agent_type="worker",
            capabilities=["gpu", "cpu"],
            services=["inference"],
            endpoints={"http": "http://localhost:8080"},
            metadata={"region": "us-east"}
        )
        
        assert request.agent_id == "agent_001"
        assert request.agent_type == "worker"
        assert len(request.capabilities) == 2
        assert len(request.services) == 1
        assert request.endpoints["http"] == "http://localhost:8080"
        assert request.metadata["region"] == "us-east"

    def test_registration_request_minimal(self):
        """Test registration request with minimal fields"""
        request = AgentRegistrationRequest(
            agent_id="agent_002",
            agent_type="specialist",
            capabilities=["storage"],
            services=["backup"],
            endpoints={"http": "http://localhost:8081"}
        )
        
        assert request.agent_id == "agent_002"
        assert request.agent_type == "specialist"
        assert request.metadata == {}


class TestAgentStatusUpdate:
    """Test agent status update model"""

    def test_status_update_creation(self):
        """Test creating a status update request"""
        request = AgentStatusUpdate(
            status="active",
            load_metrics={"cpu": 0.5, "memory": 0.6}
        )
        
        assert request.status == "active"
        assert request.load_metrics["cpu"] == 0.5
        assert request.load_metrics["memory"] == 0.6

    def test_status_update_minimal(self):
        """Test status update with only status"""
        request = AgentStatusUpdate(status="busy")
        
        assert request.status == "busy"
        assert request.load_metrics == {}

    def test_status_update_status_values(self):
        """Test valid status values"""
        valid_statuses = ["active", "inactive", "busy", "maintenance", "error"]
        
        for status in valid_statuses:
            request = AgentStatusUpdate(status=status)
            assert request.status == status

    def test_status_update_complex_metrics(self):
        """Test status update with complex load metrics"""
        request = AgentStatusUpdate(
            status="active",
            load_metrics={
                "cpu": 0.7,
                "memory": 0.8,
                "disk": 0.3,
                "network_in": 1000,
                "network_out": 500,
                "active_connections": 50
            }
        )
        
        assert len(request.load_metrics) == 6
        assert request.load_metrics["cpu"] == 0.7
        assert request.load_metrics["active_connections"] == 50

    def test_registration_request_with_all_fields(self):
        """Test agent registration with all optional fields"""
        request = AgentRegistrationRequest(
            agent_id="agent_004",
            agent_type="specialist",
            capabilities=["gpu", "storage"],
            services=["inference", "backup"],
            endpoints={"http": "http://localhost:8080", "grpc": "localhost:9090"},
            metadata={"region": "us-west", "gpu_model": "A100"}
        )
        
        assert request.agent_id == "agent_004"
        assert request.agent_type == "specialist"
        assert len(request.capabilities) == 2
        assert len(request.services) == 2
        assert len(request.endpoints) == 2
        assert request.metadata["gpu_model"] == "A100"

    def test_status_update_with_agent_id(self):
        """Test status update with detailed metrics"""
        request = AgentStatusUpdate(
            status="maintenance",
            load_metrics={"cpu": 0.1, "memory": 0.2, "gpu": 0.0}
        )
        
        assert request.status == "maintenance"
        assert request.load_metrics["gpu"] == 0.0

    def test_registration_request_empty_capabilities(self):
        """Test registration request with empty capabilities"""
        request = AgentRegistrationRequest(
            agent_id="agent_empty_caps",
            agent_type="worker",
            capabilities=[],
            services=[],
            endpoints={"http": "http://localhost:8082"}
        )
        
        assert len(request.capabilities) == 0
        assert len(request.services) == 0

    def test_status_update_empty_metrics(self):
        """Test status update with empty load metrics"""
        request = AgentStatusUpdate(
            status="active",
            load_metrics={}
        )
        
        assert request.load_metrics == {}
        assert request.status == "active"

    def test_registration_request_with_all_optional_fields(self):
        """Test registration request with all optional fields"""
        request = AgentRegistrationRequest(
            agent_id="agent_all_optional",
            agent_type="specialist",
            capabilities=["gpu", "storage"],
            services=["inference", "backup"],
            endpoints={
                "http": "http://localhost:8088",
                "grpc": "grpc://localhost:9094"
            },
            metadata={"region": "us-east", "zone": "us-east-1"}
        )
        
        assert len(request.capabilities) == 2
        assert len(request.services) == 2
        assert len(request.endpoints) == 2
        assert len(request.metadata) == 2

    def test_status_update_with_high_priority(self):
        """Test status update with high priority status"""
        request = AgentStatusUpdate(
            status="maintenance",
            load_metrics={"cpu": 0.0, "memory": 0.0}
        )
        
        assert request.status == "maintenance"
        assert request.load_metrics["cpu"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
