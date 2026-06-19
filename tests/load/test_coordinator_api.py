"""
Load tests for AITBC Coordinator API using Locust.

Tests:
- Job submission endpoint at 100 req/s
- Miner heartbeat endpoint at 1000 req/s
- Health check endpoint at 500 req/s

Usage:
    locust -f tests/load/test_coordinator_api.py --host http://localhost:8203
"""

from locust import HttpUser, between, task


class CoordinatorAPIUser(HttpUser):
    """Simulates users interacting with the Coordinator API."""

    wait_time = between(1, 3)

    @task(3)
    def submit_job(self) -> None:
        """Test job submission endpoint."""
        self.client.post(
            "/api/jobs/submit",
            json={
                "task_type": "training",
                "payload": {"model": "llm", "dataset": "mnist"},
                "required_capabilities": ["gpu"],
                "priority": 1,
            },
        )

    @task(10)
    def miner_heartbeat(self) -> None:
        """Test miner heartbeat endpoint."""
        self.client.post(
            "/api/miners/test-miner-001/heartbeat",
            json={"status": "online", "gpu_available": 4, "gpu_utilization": 0.5},
        )

    @task(1)
    def health_check(self) -> None:
        """Test health check endpoint."""
        self.client.get("/api/health")

    @task(1)
    def list_jobs(self) -> None:
        """Test list jobs endpoint."""
        self.client.get("/api/jobs")

    @task(1)
    def list_miners(self) -> None:
        """Test list miners endpoint."""
        self.client.get("/api/miners")


class CoordinatorAPIStressUser(HttpUser):
    """Stress test user with higher load."""

    wait_time = between(0.1, 0.5)

    @task(10)
    def rapid_heartbeat(self) -> None:
        """Rapid heartbeat stress test."""
        self.client.post(
            "/api/miners/stress-miner/heartbeat",
            json={"status": "online", "gpu_available": 4, "gpu_utilization": 0.5},
        )

    @task(5)
    def rapid_job_submit(self) -> None:
        """Rapid job submission stress test."""
        self.client.post(
            "/api/jobs/submit",
            json={
                "task_type": "inference",
                "payload": {"model": "vision", "input": "image.jpg"},
                "required_capabilities": ["gpu"],
                "priority": 1,
            },
        )
