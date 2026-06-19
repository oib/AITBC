"""
Load tests for AITBC Coordinator API using Locust.

Tests:
- Health check endpoint at 500 req/s

Note: This is a simplified load test that tests the working /health endpoint.
Other endpoints (swarm, hermes, training) are not currently configured in the running API.

Usage:
    locust -f tests/load/test_coordinator_api.py --host http://localhost:8203
"""

from locust import HttpUser, between, task


class CoordinatorAPIUser(HttpUser):
    """Simulates users interacting with the Coordinator API."""

    wait_time = between(1, 3)

    @task(10)
    def health_check(self) -> None:
        """Test health check endpoint."""
        self.client.get("/health")


class CoordinatorAPIStressUser(HttpUser):
    """Stress test user with higher load."""

    wait_time = between(0.1, 0.5)

    @task(10)
    def rapid_health_check(self) -> None:
        """Rapid health check stress test."""
        self.client.get("/health")
