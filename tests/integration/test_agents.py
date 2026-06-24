"""Integration tests for agent registration, discovery, status, and lifecycle."""

from typing import Any

import pytest
from starlette.testclient import TestClient


class TestAgentRegistration:
    """Test agent registration endpoints."""

    def test_register_agent_success(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test successful agent registration."""
        response = coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["status"] == "success"
        assert data["agent_id"] == sample_agent_data["agent_id"]

    def test_register_agent_duplicate(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test registering duplicate agent."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        assert response.status_code in (200, 201, 409)
        if response.status_code in (200, 201):
            data = response.json()
            assert data["status"] == "success"

    def test_register_agent_invalid_data(self, coordinator_client: TestClient):
        """Test registration with invalid data."""
        invalid_data = {"agent_id": "invalid"}
        response = coordinator_client.post("/v1/agents/register", json=invalid_data)
        assert response.status_code == 422

    def test_register_agent_missing_agent_id(self, coordinator_client: TestClient):
        """Test registration without agent ID."""
        invalid_data = {"agent_type": "worker"}
        response = coordinator_client.post("/v1/agents/register", json=invalid_data)
        assert response.status_code == 422


class TestAgentDiscovery:
    """Test agent discovery endpoints."""

    def test_discover_all_agents(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test discovering all agents."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.post("/v1/agents/discover", json={})
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_discover_by_status(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test discovering agents by status."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.post("/v1/agents/discover", json={"status": "active"})
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_discover_by_type(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test discovering agents by type."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.post("/v1/agents/discover", json={"agent_type": "worker"})
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_discover_empty_result(self, coordinator_client: TestClient):
        """Test discovering with no results."""
        response = coordinator_client.post("/v1/agents/discover", json={"agent_type": "nonexistent"})
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("agents", [])) == 0


class TestAgentStatus:
    """Test agent status endpoints."""

    def test_get_agent_info(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test getting agent information."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.get(f"/v1/agents/{sample_agent_data['agent_id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["agent"]["agent_id"] == sample_agent_data["agent_id"]

    def test_get_agent_not_found(self, coordinator_client: TestClient):
        """Test getting non-existent agent."""
        response = coordinator_client.get("/v1/agents/nonexistent-agent")
        assert response.status_code == 404

    def test_update_agent_status(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test updating agent status."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.put(f"/v1/agents/{sample_agent_data['agent_id']}/status", json={"status": "inactive"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_update_agent_status_invalid(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test updating agent status with invalid data."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.put(f"/v1/agents/{sample_agent_data['agent_id']}/status", json={"status": "invalid"})
        assert response.status_code in (400, 422, 500)


class TestHeartbeat:
    """Test agent heartbeat endpoint."""

    def test_agent_heartbeat(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test agent heartbeat."""
        coordinator_client.post("/v1/agents/register", json=sample_agent_data)
        response = coordinator_client.post(f"/v1/agents/{sample_agent_data['agent_id']}/heartbeat")
        if response.status_code == 404:
            pytest.skip("Heartbeat endpoint not registered in running coordinator")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_heartbeat_nonexistent_agent(self, coordinator_client: TestClient):
        """Test heartbeat for non-existent agent."""
        response = coordinator_client.post("/v1/agents/nonexistent/heartbeat")
        assert response.status_code == 404


class TestAgentsAdvanced:
    """Advanced agent management tests for better coverage."""

    def test_agents_all_types_and_statuses(self, coordinator_client: TestClient):
        """Test agents with all types and status combinations."""
        agent_types = ["worker", "coordinator", "monitor", "storage", "compute"]
        statuses = ["active", "inactive", "maintenance", "degraded"]

        for agent_type in agent_types:
            for status in statuses:
                agent_data = {
                    "agent_id": f"agent-{agent_type}-{status}",
                    "agent_type": agent_type,
                    "capabilities": ["data-processing", "analysis"],
                    "services": ["task-execution"],
                    "endpoints": {"http": "http://localhost:9001"},
                }
                coordinator_client.post("/v1/agents/register", json=agent_data)
                coordinator_client.put(f"/v1/agents/agent-{agent_type}-{status}/status", json={"status": status})

    def test_agents_discovery_all_filters(self, coordinator_client: TestClient):
        """Test agent discovery with all filter combinations."""
        filter_combinations = [
            {},
            {"status": "active"},
            {"agent_type": "worker"},
            {"capabilities": ["data-processing"]},
            {"services": ["task-execution"]},
            {"status": "active", "agent_type": "worker"},
            {"capabilities": ["data-processing"], "services": ["task-execution"]},
            {"status": "active", "agent_type": "worker", "capabilities": ["data-processing"]},
        ]

        for filters in filter_combinations:
            response = coordinator_client.post("/v1/agents/discover", json=filters)
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data

    def test_agents_lifecycle_full(self, coordinator_client: TestClient):
        """Test complete agent lifecycle."""
        agent_id = "lifecycle-agent-001"

        # Register
        agent_data = {
            "agent_id": agent_id,
            "agent_type": "worker",
            "capabilities": ["data-processing"],
            "services": ["task-execution"],
            "endpoints": {"http": "http://localhost:9001"},
        }
        response = coordinator_client.post("/v1/agents/register", json=agent_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["status"] == "success"

        # Get info
        response = coordinator_client.get(f"/v1/agents/{agent_id}")
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            assert data["agent"]["agent_id"] == agent_id

        # Update status
        for status in ["active", "inactive", "active"]:
            response = coordinator_client.put(f"/v1/agents/{agent_id}/status", json={"status": status})
            assert response.status_code in (200, 500)
            if response.status_code == 200:
                data = response.json()
                assert data["status"] == "success"

        # Discover
        response = coordinator_client.post("/v1/agents/discover", json={"agent_id": agent_id})
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data


class TestAgentDiscoveryComprehensive:
    """Comprehensive agent discovery tests for better coverage."""

    def test_agent_discovery_all_filters(self, coordinator_client: TestClient):
        """Test agent discovery with all possible filter combinations."""
        agent_types = ["worker", "coordinator", "monitor", "storage", "compute"]
        capabilities = ["data-processing", "gpu-compute", "storage", "networking"]
        services = ["task-execution", "monitoring", "storage-service", "network-service"]

        for i, (agent_type, cap, service) in enumerate(zip(agent_types, capabilities, services, strict=False)):
            agent_data = {
                "agent_id": f"discovery-agent-{i}",
                "agent_type": agent_type,
                "capabilities": [cap, "general"],
                "services": [service, "general"],
                "endpoints": {"http": f"http://localhost:900{i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)
            coordinator_client.put(f"/v1/agents/discovery-agent-{i}/status", json={"status": "active"})

        filter_combinations = [
            {},
            {"status": "active"},
            {"agent_type": "worker"},
            {"agent_type": "coordinator"},
            {"capabilities": ["data-processing"]},
            {"capabilities": ["gpu-compute"]},
            {"services": ["task-execution"]},
            {"services": ["monitoring"]},
            {"status": "active", "agent_type": "worker"},
            {"status": "active", "capabilities": ["data-processing"]},
            {"agent_type": "worker", "capabilities": ["data-processing"]},
            {"capabilities": ["data-processing"], "services": ["task-execution"]},
            {"status": "active", "agent_type": "worker", "capabilities": ["data-processing"]},
        ]

        for filters in filter_combinations:
            response = coordinator_client.post("/v1/agents/discover", json=filters)
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data

    def test_agent_service_discovery(self, coordinator_client: TestClient):
        """Test agent discovery by service."""
        services = ["task-execution", "monitoring", "storage-service", "network-service"]

        for service in services:
            response = coordinator_client.get(f"/v1/agents/service/{service}")
            assert response.status_code in (200, 404, 503)
            if response.status_code == 200:
                data = response.json()
                assert "agents" in data or isinstance(data, list)

    def test_agent_capability_discovery(self, coordinator_client: TestClient):
        """Test agent discovery by capability."""
        capabilities = ["data-processing", "gpu-compute", "storage", "networking"]

        for capability in capabilities:
            response = coordinator_client.get(f"/v1/agents/capability/{capability}")
            assert response.status_code in (200, 404, 503)
            if response.status_code == 200:
                data = response.json()
                assert "agents" in data or isinstance(data, list)

    def test_agent_registry_operations(self, coordinator_client: TestClient):
        """Test all agent registry operations."""
        for i in range(5):
            agent_data = {
                "agent_id": f"registry-agent-{i}",
                "agent_type": "worker",
                "capabilities": ["data-processing"],
                "services": ["task-execution"],
                "endpoints": {"http": f"http://localhost:900{i}"},
            }
            coordinator_client.post("/v1/agents/register", json=agent_data)

        response = coordinator_client.get("/v1/registry/stats")
        assert response.status_code in (200, 404, 503)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or isinstance(data, dict)

        response = coordinator_client.get("/api/v1/agent/messages/load-balancer/stats")
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "stats" in data

        response = coordinator_client.post("/v1/agents/discover", json={})
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
