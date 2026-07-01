"""Agent Coordinator API Integration Tests.

Updated to use the in-process TestClient fixture rather than a standalone
service on localhost:8107, and to exercise endpoints that exist in the current
coordinator API.
"""

from starlette.testclient import TestClient


class TestAgentCoordinatorAPI:
    """Test Agent Coordinator API endpoints using the integration test client."""

    def test_health_endpoint(self, coordinator_client: TestClient):
        """Test health check endpoint."""
        response = coordinator_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "env" in data or "python_version" in data

    def test_root_endpoint(self, coordinator_client: TestClient):
        """Test root endpoint."""
        response = coordinator_client.get("/")
        assert response.status_code in (200, 404)

    def test_agent_registration(self, coordinator_client: TestClient):
        """Test agent registration endpoint."""
        agent_data = {
            "agent_id": "api_test_agent_001",
            "public_key": "test-public-key",
            "capabilities": ["data_processing", "analysis"],
        }

        response = coordinator_client.post("/v1/agent/agents/register", json=agent_data)
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["success"] is True
        assert data["agent"]["id"] == "api_test_agent_001"

    def test_agent_discovery(self, coordinator_client: TestClient):
        """Test agent discovery endpoint."""
        response = coordinator_client.get("/v1/agent/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

    def test_messaging_stats(self, coordinator_client: TestClient):
        """Test messaging statistics endpoint."""
        response = coordinator_client.get("/v1/agent/stats")
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)


class TestAPIPerformance:
    """Test API performance and reliability."""

    def test_response_times(self, coordinator_client: TestClient):
        """Test API response times."""
        import time

        endpoints = ["/health", "/v1/agent/agents", "/v1/agent/stats"]

        for endpoint in endpoints:
            start_time = time.time()
            response = coordinator_client.get(endpoint)
            end_time = time.time()

            assert response.status_code in (200, 404)
            response_time = end_time - start_time
            assert response_time < 1.0

    def test_concurrent_requests(self, coordinator_client: TestClient):
        """Test concurrent request handling."""
        import threading

        results = []

        def make_request():
            response = coordinator_client.get("/health")
            results.append(response.status_code)

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert all(status == 200 for status in results)
        assert len(results) == 10


class TestAPIErrorHandling:
    """Test API error handling."""

    def test_nonexistent_agent(self, coordinator_client: TestClient):
        """Test requesting nonexistent agent profile.

        The current API returns a profile with empty capabilities for unknown
        agents rather than a 404.
        """
        response = coordinator_client.get("/v1/agent/agents/nonexistent_agent/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "nonexistent_agent"
        assert data["capabilities"] == []

    def test_invalid_agent_data(self, coordinator_client: TestClient):
        """Test invalid agent registration data."""
        invalid_data = {
            "agent_id": "",  # Empty agent ID
            "public_key": "test-key",
        }

        response = coordinator_client.post("/v1/agent/agents/register", json=invalid_data)
        assert response.status_code == 422

    def test_invalid_message_data(self, coordinator_client: TestClient):
        """Test invalid message send data."""
        invalid_message = {"invalid_field": "invalid_value"}

        response = coordinator_client.post("/v1/agent/messages/send", json=invalid_message)
        assert response.status_code == 422
