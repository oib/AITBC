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

    def test_no_agent_mock_routes_are_registered(self, coordinator_client: TestClient):
        """Assert absence against the route table, not a status code.

        A 404 on /v1/agent/agents/{id}/profile is ambiguous: a live route
        would answer the same way for an unknown id. The route table is not.
        The trailing slash matters — /v1/agent-identity and
        /v1/agent-performance are real, separate families.
        """
        paths = [getattr(r, "path", "") for r in coordinator_client.app.routes]
        assert len(paths) > 100, f"route table looks unpopulated ({len(paths)}) - pin would be vacuous"
        offenders = [p for p in paths if p.startswith("/v1/agent/")]
        assert offenders == [], f"mock agent router is back: {offenders}"

    def test_swarm_routes_absent(self, coordinator_client: TestClient):
        for path in ("/v1/swarm/tasks/submit", "/v1/swarm/status", "/v1/swarm/nodes"):
            assert coordinator_client.get(path).status_code == 404

    def test_agent_mock_routes_absent(self, coordinator_client: TestClient):
        """Every /v1/agent/* path the deleted suites exercised.

        test_agents.py and the agent half of test_agent_coordinator_api.py kept
        asserting these answered; the paths are listed here so their removal
        stays pinned rather than merely untested.
        """
        for path in (
            "/v1/agent/agents",
            "/v1/agent/agents/some-agent/profile",
            "/v1/agent/messages/some-agent",
            "/v1/agent/messages/load-balancer/stats",
            "/v1/agent/stats",
            "/v1/agent/health",
        ):
            assert coordinator_client.get(path).status_code == 404
        for path in (
            "/v1/agent/agents/register",
            "/v1/agent/agents/some-agent/heartbeat",
            "/v1/agent/messages/send",
        ):
            assert coordinator_client.post(path, json={}).status_code == 404

    def test_monitor_mock_routes_absent(self, coordinator_client: TestClient):
        for path in ("/v1/dashboard", "/v1/dashboard/history", "/v1/miners"):
            assert coordinator_client.get(path).status_code == 404
