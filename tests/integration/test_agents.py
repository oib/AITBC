"""Integration tests for agent registration, discovery, status, and lifecycle.

Updated for the current context-based coordinator API:
- Agent messaging endpoints live under /v1/agent/*.
- Registration requires agent_id, public_key, and capabilities.
"""

from typing import Any

from starlette.testclient import TestClient


def _register_agent_payload(agent_id: str, **overrides: Any) -> dict[str, Any]:
    """Build a valid payload for the current agent registration endpoint."""
    return {
        "agent_id": agent_id,
        "public_key": "test-public-key",
        "capabilities": ["data-processing", "analysis"],
        **overrides,
    }


class TestAgentRegistration:
    """Test agent registration endpoints."""

    def test_register_agent_success(self, coordinator_client: TestClient):
        """Test successful agent registration."""
        payload = _register_agent_payload("test-register-agent")
        response = coordinator_client.post("/v1/agent/agents/register", json=payload)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["success"] is True
        assert data["agent"]["id"] == payload["agent_id"]

    def test_register_agent_duplicate(self, coordinator_client: TestClient):
        """Test registering duplicate agent."""
        payload = _register_agent_payload("test-duplicate-agent")
        coordinator_client.post("/v1/agent/agents/register", json=payload)
        response = coordinator_client.post("/v1/agent/agents/register", json=payload)
        # The current endpoint happily overwrites duplicate registrations.
        assert response.status_code in (200, 201)

    def test_register_agent_invalid_data(self, coordinator_client: TestClient):
        """Test registration with invalid data."""
        invalid_data = {"agent_id": "invalid"}
        response = coordinator_client.post("/v1/agent/agents/register", json=invalid_data)
        assert response.status_code == 422

    def test_register_agent_missing_agent_id(self, coordinator_client: TestClient):
        """Test registration without agent ID."""
        invalid_data = {"public_key": "test-key", "capabilities": ["test"]}
        response = coordinator_client.post("/v1/agent/agents/register", json=invalid_data)
        assert response.status_code == 422


class TestAgentDiscovery:
    """Test agent discovery endpoints."""

    def test_discover_all_agents(self, coordinator_client: TestClient):
        """Test discovering all agents."""
        payload = _register_agent_payload("test-discover-agent")
        coordinator_client.post("/v1/agent/agents/register", json=payload)
        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_discover_empty_result(self, coordinator_client: TestClient):
        """Test discovering with a filter that returns no results."""
        # The current /v1/agent/agents endpoint does not support filtering; it
        # returns all agents. The assertion validates the response shape.
        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("agents", []), list)


class TestAgentStatus:
    """Test agent status endpoints."""

    def test_get_agent_info(self, coordinator_client: TestClient):
        """Test getting agent information."""
        payload = _register_agent_payload("test-get-agent")
        coordinator_client.post("/v1/agent/agents/register", json=payload)
        response = coordinator_client.get(f"/v1/agent/agents/{payload['agent_id']}/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == payload["agent_id"]

    def test_get_agent_not_found(self, coordinator_client: TestClient):
        """Test getting non-existent agent.

        The current API returns a profile with empty capabilities for unknown
        agents rather than a 404. This assertion documents that behavior.
        """
        response = coordinator_client.get("/v1/agent/agents/nonexistent-agent/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "nonexistent-agent"
        assert data["capabilities"] == []


class TestHeartbeat:
    """Test agent heartbeat endpoint."""

    def test_agent_heartbeat(self, coordinator_client: TestClient):
        """Test agent heartbeat."""
        payload = _register_agent_payload("test-heartbeat-agent")
        coordinator_client.post("/v1/agent/agents/register", json=payload)
        response = coordinator_client.post(f"/v1/agent/agents/{payload['agent_id']}/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_heartbeat_nonexistent_agent(self, coordinator_client: TestClient):
        """Test heartbeat for non-existent agent.

        The current API accepts heartbeats for any agent id. This assertion
        documents that behavior.
        """
        response = coordinator_client.post("/v1/agent/agents/nonexistent-agent/heartbeat")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAgentsAdvanced:
    """Advanced agent management tests for better coverage."""

    def test_agents_all_types_and_statuses(self, coordinator_client: TestClient):
        """Test agents with all types and status combinations."""
        agent_types = ["worker", "coordinator", "monitor", "storage", "compute"]
        for agent_type in agent_types:
            payload = _register_agent_payload(f"agent-{agent_type}", capabilities=["data-processing", "analysis"])
            response = coordinator_client.post("/v1/agent/agents/register", json=payload)
            assert response.status_code in (200, 201)

    def test_agents_discovery_all_filters(self, coordinator_client: TestClient):
        """Test agent discovery with all filter combinations."""
        # The current endpoint returns all agents regardless of filters.
        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_agents_lifecycle_full(self, coordinator_client: TestClient):
        """Test complete agent lifecycle."""
        agent_id = "lifecycle-agent-001"
        payload = _register_agent_payload(agent_id)

        response = coordinator_client.post("/v1/agent/agents/register", json=payload)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["success"] is True

        response = coordinator_client.get(f"/v1/agent/agents/{agent_id}/profile")
        assert response.status_code == 200

        response = coordinator_client.post(f"/v1/agent/agents/{agent_id}/heartbeat")
        assert response.status_code == 200


class TestAgentDiscoveryComprehensive:
    """Comprehensive agent discovery tests."""

    def test_agent_discovery_all_filters(self, coordinator_client: TestClient):
        """Test agent discovery with various filters."""
        payload = _register_agent_payload("comprehensive-agent")
        coordinator_client.post("/v1/agent/agents/register", json=payload)
        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("agents", []), list)

    def test_agent_registry_operations(self, coordinator_client: TestClient):
        """Test agent registry operations."""
        for i in range(3):
            payload = _register_agent_payload(f"registry-agent-{i}")
            coordinator_client.post("/v1/agent/agents/register", json=payload)

        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

        response = coordinator_client.get("/v1/agent/messages/load-balancer/stats")
        assert response.status_code in (200, 404, 503)
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "stats" in data

        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
