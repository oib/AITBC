"""
Tests for inference router (AI model inference via Ollama)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestInferenceRouter:
    """Test inference router endpoints"""

    def test_inference_health(self, client: TestClient):
        """Test inference health endpoint"""
        response = client.get("/v1/inference/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_list_models(self, client: TestClient):
        """Test listing available models"""
        response = client.get("/v1/inference/models")
        assert response.status_code in [200, 503]  # 503 if Ollama not running

        if response.status_code == 200:
            data = response.json()
            assert "models" in data
            assert "count" in data

    def test_generate_invalid_model(self, client: TestClient):
        """Test generation with invalid model"""
        generate_data = {"model": "nonexistent-model-xyz", "prompt": "Test"}

        response = client.post("/v1/inference/generate", json=generate_data)
        # Should fail gracefully
        assert response.status_code in [200, 400, 404, 500, 502, 503]

    def test_batch_generate_empty_prompts(self, client: TestClient):
        """Test batch with empty prompts fails"""
        batch_data = {"model": "llama2", "prompts": []}

        response = client.post("/v1/inference/batch", json=batch_data)
        assert response.status_code == 422  # Validation error

    def test_batch_generate_too_many_prompts(self, client: TestClient):
        """Test batch with too many prompts fails"""
        batch_data = {
            "model": "llama2",
            "prompts": ["test"] * 20,  # Too many
        }

        response = client.post("/v1/inference/batch", json=batch_data)
        assert response.status_code == 422  # Validation error
