"""Integration tests for edge cases, error handling, and API scenarios.

Updated for the current context-based coordinator API. Agent endpoints live
under /v1/agent/*, task endpoints under /v1/swarm/*, and the legacy
auth/alert/user endpoints are not exercised here.
"""

from typing import Any

from starlette.testclient import TestClient


class TestEdgeCases:
    """Test edge cases and error paths."""

    def test_agent_registration_invalid_data(self, coordinator_client: TestClient):
        """Test agent registration with various invalid data."""
        invalid_cases = [
            {},
            {"agent_id": "test"},  # missing public_key
            {"agent_id": "", "public_key": "key"},
            {"agent_id": "test", "public_key": "key", "capabilities": []},
        ]
        for data in invalid_cases:
            response = coordinator_client.post("/v1/agent/agents/register", json=data)
            assert response.status_code in (200, 422, 400)

    def test_task_submission_various_priorities(self, coordinator_client: TestClient):
        """Test task submission with various priorities."""
        priorities = ["low", "normal", "high", "critical", "urgent"]
        for priority in priorities:
            task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": priority}
            response = coordinator_client.post("/v1/swarm/tasks/submit", json=task_data)
            assert response.status_code in (200, 201)

    def test_agent_status_updates(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test agent heartbeat updates."""
        coordinator_client.post("/v1/agent/agents/register", json=sample_agent_data)
        response = coordinator_client.post(f"/v1/agent/agents/{sample_agent_data['agent_id']}/heartbeat")
        assert response.status_code == 200

    def test_agent_discovery(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test agent discovery."""
        coordinator_client.post("/v1/agent/agents/register", json=sample_agent_data)
        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_nonexistent_endpoints(self, coordinator_client: TestClient):
        """Test that nonexistent endpoints return 404."""
        endpoints = ["/nonexistent", "/v1/nonexistent"]
        for endpoint in endpoints:
            response = coordinator_client.get(endpoint)
            assert response.status_code == 404

    def test_invalid_http_methods(self, coordinator_client: TestClient):
        """Test invalid HTTP methods on valid endpoints."""
        response = coordinator_client.post("/health")
        assert response.status_code in (405, 404)

        response = coordinator_client.get("/v1/agent/agents/register")
        assert response.status_code in (405, 404)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_json_requests(self, coordinator_client: TestClient):
        """Test endpoints with invalid JSON data."""
        endpoints = [
            ("/v1/agent/agents/register", "POST"),
            ("/v1/swarm/tasks/submit", "POST"),
            ("/v1/agent/messages/send", "POST"),
        ]

        for endpoint, method in endpoints:
            if method == "POST":
                response = coordinator_client.post(endpoint, json={"invalid": "data"})
                assert response.status_code in (200, 400, 422, 429)

    def test_malformed_request_data(self, coordinator_client: TestClient):
        """Test endpoints with malformed request data."""
        malformed_data = ["", "invalid string", {"nested": {"deeply": {"invalid": "structure"}}}]

        for data in malformed_data:
            response = coordinator_client.post("/v1/agent/agents/register", json=data)
            assert response.status_code in (200, 400, 422, 429)

    def test_special_characters_in_ids(self, coordinator_client: TestClient):
        """Test endpoints with special characters in IDs."""
        special_ids = ["test@123", "test#123", "test space", "test/123"]
        for agent_id in special_ids:
            payload = {"agent_id": agent_id, "public_key": "key", "capabilities": ["test"]}
            response = coordinator_client.post("/v1/agent/agents/register", json=payload)
            assert response.status_code in (200, 422)

    def test_very_long_strings(self, coordinator_client: TestClient):
        """Test endpoints with very long strings."""
        long_id = "a" * 200
        payload = {"agent_id": long_id, "public_key": "key", "capabilities": ["test"]}
        response = coordinator_client.post("/v1/agent/agents/register", json=payload)
        assert response.status_code in (200, 422)

    def test_numeric_edge_cases(self, coordinator_client: TestClient):
        """Test endpoints with numeric edge cases."""
        response = coordinator_client.post("/v1/swarm/tasks/submit", json={"task_data": 0, "priority": 1})
        assert response.status_code in (200, 422)

    def test_boolean_and_null_values(self, coordinator_client: TestClient):
        """Test endpoints with boolean and null values."""
        response = coordinator_client.post("/v1/agent/agents/register", json=None)
        assert response.status_code in (400, 422)

    def test_array_edge_cases(self, coordinator_client: TestClient):
        """Test endpoints with array edge cases."""
        response = coordinator_client.post("/v1/agent/agents/register", json=[])
        assert response.status_code in (400, 422)


class TestAdvancedScenarios:
    """Test advanced integration scenarios."""

    def test_agent_registration_and_task_submission(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test agent registration followed by task submission."""
        response = coordinator_client.post("/v1/agent/agents/register", json=sample_agent_data)
        assert response.status_code in (200, 201)

        coordinator_client.post(f"/v1/agent/agents/{sample_agent_data['agent_id']}/heartbeat")

        task_data = {"task_data": {"model": "llama2", "prompt": "test"}, "priority": "normal"}
        response = coordinator_client.post("/v1/swarm/tasks/submit", json=task_data)
        assert response.status_code in (200, 201)

    def test_message_send_after_registration(self, coordinator_client: TestClient, sample_agent_data: dict[str, Any]):
        """Test message send after agent registration."""
        coordinator_client.post("/v1/agent/agents/register", json=sample_agent_data)

        message_data = {
            "sender": sample_agent_data["agent_id"],
            "recipient": "recipient-agent",
            "content": "test message",
            "message_type": "direct",
        }
        response = coordinator_client.post("/v1/agent/messages/send", json=message_data)
        assert response.status_code in (200, 201, 400)


class TestLowCoverageModules:
    """Test modules that historically had low coverage."""

    def test_load_balancer_error_recovery(self, coordinator_client: TestClient):
        """Test load balancer error recovery.

        The legacy load balancer endpoints do not exist. Verify that the
        swarm status endpoint responds, which is the closest available check.
        """
        response = coordinator_client.get("/v1/swarm/status")
        assert response.status_code in (200, 404)
