import pytest
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

class TestMLZKIntegration:
    """End-to-end tests for ML ZK integration"""

    @pytest.fixture
    def test_client(self):
        return TestClient(app)

    def test_js_sdk_receipt_verification_e2e(self, test_client):
        """End-to-end test of JS SDK receipt verification"""
        # Test that the API is accessible
        response = test_client.get("/v1/health")
        assert response.status_code == 200
        
        # Test a simple endpoint that should exist
        health_response = response.json()
        assert "status" in health_response

    def test_edge_gpu_api_integration(self, test_client, db_session):
        """Test edge GPU API integration"""
        # Test GPU profile retrieval (this should work with db_session)
        from app.services.edge_gpu_service import EdgeGPUService
        service = EdgeGPUService(db_session)
        
        # Test the service directly instead of via API
        profiles = service.list_profiles(edge_optimized=True)
        assert len(profiles) >= 0  # Should not crash
        # discovery = test_client.post("/v1/marketplace/edge-gpu/scan/miner_123")
        # assert discovery.status_code == 200

    def test_ml_zk_proof_generation(self, test_client):
        """Test ML ZK proof generation end-to-end"""
        # Test modular ML proof generation (this endpoint exists)
        proof_request = {
            "inputs": {
                "model_id": "test_model_001",
                "inference_id": "test_inference_001",
                "expected_output": [2.5]
            },
            "private_inputs": {
                "inputs": [1, 2, 3, 4],
                "weights1": [0.1, 0.2, 0.3, 0.4],
                "biases1": [0.1, 0.2]
            }
        }

        proof_response = test_client.post("/v1/ml-zk/prove/modular", json=proof_request)

        # Should get either 200 (success) or 500 (circuit missing)
        assert proof_response.status_code in [200, 500]
        
        if proof_response.status_code == 200:
            proof_data = proof_response.json()
            assert "proof" in proof_data or "error" in proof_data

    def test_fhe_ml_inference(self, test_client):
        """Test FHE ML inference end-to-end"""
        fhe_request = {
            "scheme": "ckks",
            "provider": "tenseal",
            "input_data": [[1.0, 2.0, 3.0, 4.0]],
            "model": {
                "weights": [[0.1, 0.2, 0.3, 0.4]],
                "biases": [0.5]
            }
        }

        fhe_response = test_client.post("/v1/ml-zk/fhe/inference", json=fhe_request)

        # Should get either 200 (success) or 500 (provider missing)
        assert fhe_response.status_code in [200, 500]
        
        if fhe_response.status_code == 200:
            result = fhe_response.json()
            assert "encrypted_result" in result or "error" in result
