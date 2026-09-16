"""Integration tests for edge cases, error handling, and API scenarios.

Updated for the current context-based coordinator API. The /v1/agent/* and
/v1/swarm/* mock routers were removed — they fabricated registries and
responses behind settings.debug. What remains here asserts their honest
absence plus generic edge-case behavior on real endpoints.
"""

from starlette.testclient import TestClient


class TestEdgeCases:
    """Test edge cases and error paths."""

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


class TestRemovedMockRouters:
    """The debug-gated mock routers were deleted — pin their honest absence.

    These tests run with DEBUG=true (see conftest); a route that only exists
    under that gate would answer here, so 404 proves removal rather than just
    production gating.
    """

    def test_swarm_routes_absent(self, coordinator_client: TestClient):
        for path in ("/v1/swarm/tasks/submit", "/v1/swarm/status", "/v1/swarm/nodes"):
            assert coordinator_client.get(path).status_code == 404

    def test_agent_mock_routes_absent(self, coordinator_client: TestClient):
        for path in (
            "/v1/agent/agents",
            "/v1/agent/messages/some-agent",
            "/v1/agent/stats",
            "/v1/agent/health",
        ):
            assert coordinator_client.get(path).status_code == 404
        assert coordinator_client.post("/v1/agent/agents/register", json={}).status_code == 404

    def test_monitor_mock_routes_absent(self, coordinator_client: TestClient):
        for path in ("/v1/dashboard", "/v1/dashboard/history", "/v1/miners"):
            assert coordinator_client.get(path).status_code == 404
