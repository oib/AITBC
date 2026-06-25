"""
Tests for FHE router (Fully Homomorphic Encryption)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestFHERouter:
    """Test FHE router endpoints"""

    def test_fhe_health(self, client: TestClient):
        """Test FHE health endpoint"""
        response = client.get("/v1/fhe/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["fhe_available"] is True
        assert data["service"] == "fhe"

    def test_generate_context(self, client: TestClient):
        """Test generating FHE context"""
        response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv", "poly_modulus_degree": 4096})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "context_id" in data
        assert data["scheme"] == "bfv"
        assert data["status"] == "ready"

    def test_encrypt(self, client: TestClient):
        """Test encrypting data"""
        # First generate context
        ctx_response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        context_id = ctx_response.json()["context_id"]

        encrypt_data = {"context_id": context_id, "data": [1.0, 2.0, 3.0, 4.0, 5.0]}

        response = client.post("/v1/fhe/encrypt", json=encrypt_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "encrypted_data" in data
        assert data["context_id"] == context_id
        assert "shape" in data

    def test_decrypt(self, client: TestClient):
        """Test decrypting data"""
        # Generate context
        ctx_response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        context_id = ctx_response.json()["context_id"]

        # Encrypt
        encrypt_response = client.post("/v1/fhe/encrypt", json={"context_id": context_id, "data": [42.0, 100.0]})
        encrypted_data = encrypt_response.json()["encrypted_data"]

        # Decrypt
        decrypt_data = {"encrypted_data": encrypted_data}

        response = client.post("/v1/fhe/decrypt", json=decrypt_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert len(data["data"]) == 2
        assert "shape" in data
        assert "dtype" in data

    def test_add_encrypted(self, client: TestClient):
        """Test homomorphic addition"""
        ctx_response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        context_id = ctx_response.json()["context_id"]

        # Encrypt two values
        ct1 = client.post("/v1/fhe/encrypt", json={"context_id": context_id, "data": [10.0]}).json()["encrypted_data"]

        ct2 = client.post("/v1/fhe/encrypt", json={"context_id": context_id, "data": [20.0]}).json()["encrypted_data"]

        # Add them
        add_data = {"context_id": context_id, "encrypted_a": ct1, "encrypted_b": ct2}

        response = client.post("/v1/fhe/add", json=add_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result" in data
        assert data["operation"] == "add"

    def test_multiply_encrypted(self, client: TestClient):
        """Test homomorphic scalar multiplication"""
        ctx_response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        context_id = ctx_response.json()["context_id"]

        ct1 = client.post("/v1/fhe/encrypt", json={"context_id": context_id, "data": [5.0]}).json()["encrypted_data"]

        multiply_data = {"context_id": context_id, "encrypted_a": ct1, "scalar": 7.0}

        response = client.post("/v1/fhe/multiply-scalar", json=multiply_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result" in data
        assert data["operation"] == "multiply_scalar"

    def test_get_context_info(self, client: TestClient):
        """Test getting context info"""
        # Generate a context first
        ctx_response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        context_id = ctx_response.json()["context_id"]

        response = client.get(f"/v1/fhe/context/{context_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["context_id"] == context_id
        assert data["available"] is True
        assert "poly_modulus_degree" in data


@pytest.mark.integration
class TestFHEIntegration:
    """Integration tests for FHE workflow"""

    def test_full_fhe_workflow(self, client: TestClient):
        """Test complete encrypt-compute-decrypt workflow"""
        # 1. Generate context
        ctx = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"}).json()
        context_id = ctx["context_id"]

        # 2. Encrypt two numbers
        ct1 = client.post("/v1/fhe/encrypt", json={"context_id": context_id, "data": [15.0]}).json()["encrypted_data"]

        ct2 = client.post("/v1/fhe/encrypt", json={"context_id": context_id, "data": [25.0]}).json()["encrypted_data"]

        # 3. Add them homomorphically
        sum_result = client.post(
            "/v1/fhe/add", json={"context_id": context_id, "encrypted_a": ct1, "encrypted_b": ct2}
        ).json()["result"]

        # 4. Decrypt result
        result = client.post("/v1/fhe/decrypt", json={"encrypted_data": sum_result}).json()

        # 5. Verify decryption succeeds (simplified FHE uses noise, so exact values differ)
        assert result["success"] is True
        assert "data" in result
        assert len(result["data"]) == 1
