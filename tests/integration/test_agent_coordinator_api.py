"""Agent Coordinator API Integration Tests.

Uses the in-process TestClient fixture rather than a standalone service on
localhost:8107.

The /v1/agent/* mock router this file used to exercise (agents/register,
agents, stats, messages/*) was removed in 73b3e9413 and 15d467e19 — it
fabricated a registry and responses behind settings.debug. Its honest absence
is pinned by test_integration_scenarios.py::TestRemovedMockRouters, so what
remains here covers only endpoints that actually exist.
"""

import threading
import time

from starlette.testclient import TestClient

# Real, unauthenticated endpoints. Every one is asserted to return exactly 200:
# the previous "in (200, 404)" tolerance is what let this file keep passing
# against routes that had already been deleted.
LIVE_ENDPOINTS = (
    "/health",
    "/v1/agents/supported",
    "/v1/agent-identity/registry/health",
)


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


class TestAPIPerformance:
    """Test API performance and reliability."""

    def test_response_times(self, coordinator_client: TestClient):
        """Test API response times."""
        for endpoint in LIVE_ENDPOINTS:
            start_time = time.time()
            response = coordinator_client.get(endpoint)
            end_time = time.time()

            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            response_time = end_time - start_time
            assert response_time < 1.0

    def test_concurrent_requests(self, coordinator_client: TestClient):
        """Test concurrent request handling."""
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
