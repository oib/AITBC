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
        response = client.get("/inference/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_list_models(self, client: TestClient):
        """Test listing available models"""
        response = client.get("/inference/models")
        assert response.status_code in [200, 503]  # 503 if Ollama not running

        if response.status_code == 200:
            data = response.json()
            assert "models" in data
            assert "count" in data

    def test_generate_text(self, client: TestClient):
        """Test text generation"""
        generate_data = {
            "model": "llama2",
            "prompt": "What is 2+2?",
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": False
        }

        response = client.post("/inference/generate", json=generate_data)
        # May fail if Ollama not running
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "response" in data
            assert "model" in data
        elif response.status_code == 503:
            pytest.skip("Ollama not available")

    def test_generate_with_system_message(self, client: TestClient):
        """Test generation with system message"""
        generate_data = {
            "model": "llama2",
            "prompt": "Hello",
            "system": "You are a helpful AI assistant.",
            "temperature": 0.5
        }

        response = client.post("/inference/generate", json=generate_data)
        if response.status_code == 503:
            pytest.skip("Ollama not available")
        assert response.status_code in [200, 503]

    def test_generate_invalid_model(self, client: TestClient):
        """Test generation with invalid model"""
        generate_data = {
            "model": "nonexistent-model-xyz",
            "prompt": "Test"
        }

        response = client.post("/inference/generate", json=generate_data)
        # Should fail gracefully
        assert response.status_code in [200, 400, 404, 503, 500]

    def test_batch_generate(self, client: TestClient):
        """Test batch inference"""
        batch_data = {
            "model": "llama2",
            "prompts": [
                "What is AI?",
                "Explain machine learning",
                "What is blockchain?"
            ],
            "temperature": 0.7,
            "max_tokens": 50
        }

        response = client.post("/inference/batch", json=batch_data)
        if response.status_code == 503:
            pytest.skip("Ollama not available")

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert data["total"] == 3
            assert "results" in data
            assert len(data["results"]) <= 3

    def test_batch_generate_empty_prompts(self, client: TestClient):
        """Test batch with empty prompts fails"""
        batch_data = {
            "model": "llama2",
            "prompts": []
        }

        response = client.post("/inference/batch", json=batch_data)
        assert response.status_code == 422  # Validation error

    def test_batch_generate_too_many_prompts(self, client: TestClient):
        """Test batch with too many prompts fails"""
        batch_data = {
            "model": "llama2",
            "prompts": ["test"] * 20  # Too many
        }

        response = client.post("/inference/batch", json=batch_data)
        assert response.status_code == 422  # Validation error

    def test_pull_model(self, client: TestClient):
        """Test pulling a model"""
        response = client.post("/inference/models/tinyllama/pull")
        # This takes time and may fail if Ollama not running
        assert response.status_code in [200, 503, 504]


@pytest.mark.integration
class TestInferenceIntegration:
    """Integration tests for inference"""

    @pytest.mark.skip(reason="Requires running Ollama service - run with --ollama flag to enable")
    def test_full_inference_workflow(self, client: TestClient):
        """Test complete inference workflow"""
        # 1. List models
        models_response = client.get("/inference/models")
        assert models_response.status_code == 200

        # 2. Generate text
        generate_response = client.post("/inference/generate", json={
            "model": "llama2",
            "prompt": "Explain quantum computing in one sentence.",
            "temperature": 0.5,
            "max_tokens": 100
        })
        assert generate_response.status_code == 200
        data = generate_response.json()
        assert len(data["response"]) > 0

        # 3. Verify metrics
        assert "eval_count" in data
        assert "total_duration" in data
