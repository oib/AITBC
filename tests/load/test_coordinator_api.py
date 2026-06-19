"""
Load tests for AITBC Coordinator API using Locust.

Tests:
- Health check endpoint at 500 req/s
- Training job submission endpoint at 100 req/s (requires DEBUG=true + ENABLE_MOCK_TRAINING=true)

Note: Training job submission endpoint is only available when debug mode is enabled.
For production load testing, only the health endpoint is tested.

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

    @task(2)
    def submit_training_job(self) -> None:
        """Test job submission endpoint (requires debug mode)."""
        job_data = {
            "model_type": "llm",
            "dataset_id": "dataset-001",
            "hyperparameters": {"learning_rate": 0.001, "batch_size": 32},
            "epochs": 10,
            "gpu_count": 2,
            "memory_gb": 32,
        }
        self.client.post("/v1/training/jobs", json=job_data)


class CoordinatorAPIStressUser(HttpUser):
    """Stress test user with higher load."""

    wait_time = between(0.1, 0.5)

    @task(10)
    def rapid_health_check(self) -> None:
        """Rapid health check stress test."""
        self.client.get("/health")

    @task(5)
    def rapid_job_submission(self) -> None:
        """Rapid job submission stress test (requires debug mode)."""
        job_data = {
            "model_type": "vision",
            "dataset_id": "cifar10",
            "hyperparameters": {"learning_rate": 0.01, "batch_size": 16},
            "epochs": 5,
            "gpu_count": 1,
            "memory_gb": 16,
        }
        self.client.post("/v1/training/jobs", json=job_data)


class CoordinatorAPIProductionUser(HttpUser):
    """Production load test user (only health endpoint)."""

    wait_time = between(0.5, 2)

    @task(10)
    def health_check(self) -> None:
        """Test health check endpoint."""
        self.client.get("/health")
