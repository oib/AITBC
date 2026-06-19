"""
Tests for training router (AI model training)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestTrainingRouter:
    """Test training router endpoints"""

    def test_create_training_job(self, client: TestClient):
        """Test creating a training job"""
        job_data = {
            "model_type": "llm",
            "dataset_id": "dataset-001",
            "hyperparameters": {"learning_rate": 0.001, "batch_size": 32, "optimizer": "adam"},
            "epochs": 10,
            "gpu_count": 2,
            "memory_gb": 32,
        }

        response = client.post("/v1/training/jobs", json=job_data)
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "created"

    def test_get_training_job(self, client: TestClient):
        """Test getting training job by ID"""
        # Create job first
        create_response = client.post(
            "/training/jobs", json={"model_type": "resnet", "dataset_id": "imagenet-train", "epochs": 5}
        )
        job_id = create_response.json()["job"]["id"]

        # Get job
        response = client.get(f"/training/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["model_type"] == "resnet"

    def test_list_training_jobs(self, client: TestClient):
        """Test listing all training jobs"""
        response = client.get("/training/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "count" in data

    def test_list_jobs_filter_by_status(self, client: TestClient):
        """Test filtering jobs by status"""
        response = client.get("/training/jobs?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert all(j["status"] == "pending" for j in data["jobs"])

    def test_start_training_job(self, client: TestClient):
        """Test starting a pending training job"""
        # Create pending job
        create_response = client.post("/training/jobs", json={"model_type": "bert", "dataset_id": "corpus-001", "epochs": 3})
        job_id = create_response.json()["job"]["id"]

        # Start it
        response = client.post(f"/training/jobs/{job_id}/start")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job"]["status"] == "running"

    def test_update_training_progress(self, client: TestClient):
        """Test updating training progress"""
        # Create and start job
        create_response = client.post("/training/jobs", json={"model_type": "gpt", "dataset_id": "text-corpus"})
        job_id = create_response.json()["job"]["id"]
        client.post(f"/training/jobs/{job_id}/start")

        # Update progress
        progress_data = {
            "job_id": job_id,
            "epoch": 5,
            "step": 100,
            "loss": 0.0234,
            "accuracy": 0.95,
            "validation_loss": 0.0256,
        }

        response = client.post("/training/progress", json=progress_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job"]["progress"]["current_epoch"] == 5

    def test_complete_training_job(self, client: TestClient):
        """Test completing a training job"""
        # Create and start job
        create_response = client.post("/training/jobs", json={"model_type": "classifier", "dataset_id": "mnist", "epochs": 1})
        job_id = create_response.json()["job"]["id"]
        client.post(f"/training/jobs/{job_id}/start")

        # Complete it
        response = client.post(f"/training/jobs/{job_id}/complete", json={"checkpoint_url": "s3://models/checkpoint-001.pt"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job"]["status"] == "completed"

    def test_cancel_training_job(self, client: TestClient):
        """Test cancelling a training job"""
        # Create job
        create_response = client.post("/training/jobs", json={"model_type": "test-model", "dataset_id": "test-data"})
        job_id = create_response.json()["job"]["id"]

        # Cancel it
        response = client.post(f"/training/jobs/{job_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["job"]["status"] == "cancelled"

    def test_get_training_logs(self, client: TestClient):
        """Test getting training logs"""
        # Create job with some progress
        create_response = client.post("/training/jobs", json={"model_type": "log-test", "dataset_id": "data"})
        job_id = create_response.json()["job"]["id"]

        # Get logs
        response = client.get(f"/training/jobs/{job_id}/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "count" in data

    def test_training_stats(self, client: TestClient):
        """Test getting training statistics"""
        response = client.get("/training/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_jobs" in data
        assert "running" in data
        assert "completed" in data
        assert "failed" in data
        assert "queued" in data

    def test_training_health(self, client: TestClient):
        """Test training health endpoint"""
        response = client.get("/training/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "max_concurrent" in data


@pytest.mark.integration
class TestTrainingIntegration:
    """Integration tests for training workflow"""

    def test_full_training_lifecycle(self, client: TestClient):
        """Test complete training lifecycle"""
        # 1. Create job
        create_response = client.post(
            "/training/jobs",
            json={
                "model_type": "integration-model",
                "dataset_id": "integration-dataset",
                "hyperparameters": {"learning_rate": 0.01, "batch_size": 16},
                "epochs": 3,
                "gpu_count": 1,
            },
        )
        job_id = create_response.json()["job"]["id"]

        # 2. Start training
        client.post(f"/training/jobs/{job_id}/start")

        # 3. Simulate training progress
        for epoch in range(1, 4):
            client.post(
                "/training/progress",
                json={
                    "job_id": job_id,
                    "epoch": epoch,
                    "step": epoch * 100,
                    "loss": 0.5 / epoch,
                    "accuracy": 0.6 + (epoch * 0.1),
                    "validation_loss": 0.55 / epoch,
                },
            )

        # 4. Complete training
        complete_response = client.post(
            f"/training/jobs/{job_id}/complete", json={"checkpoint_url": "s3://integration/checkpoint.pt"}
        )

        # 5. Verify completed
        assert complete_response.json()["job"]["status"] == "completed"
        assert complete_response.json()["job"]["metrics"]["accuracy"] > 0.8
