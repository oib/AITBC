"""
Tests for FHE router (Fully Homomorphic Encryption)

ponytail: The FHE implementation is disabled; these tests verify that the
endpoints require authentication and return 501 instead of exposing the
insecure BFV implementation.
"""

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token


def _auth_headers(client: TestClient) -> None:
    """Attach a valid JWT to the test client for FHE routes."""
    token = create_access_token("test_user", "client")
    client.headers = {"Authorization": f"Bearer {token}"}


@pytest.mark.unit
class TestFHERouter:
    """Test FHE router endpoints are disabled and protected."""

    def test_fhe_health_requires_auth(self, client: TestClient):
        """FHE health endpoint requires authentication."""
        response = client.get("/v1/fhe/health")
        assert response.status_code == 401

    def test_fhe_health_disabled(self, client: TestClient):
        """FHE health endpoint reports disabled when authenticated."""
        _auth_headers(client)
        response = client.get("/v1/fhe/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"
        assert data["fhe_available"] is False
        assert data["service"] == "fhe"

    def test_generate_context_disabled(self, client: TestClient):
        """Generating an FHE context is disabled."""
        _auth_headers(client)
        response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv", "poly_modulus_degree": 4096})
        assert response.status_code == 501

    def test_encrypt_disabled(self, client: TestClient):
        """Encrypt is disabled and requires auth."""
        _auth_headers(client)
        response = client.post("/v1/fhe/encrypt", json={"context_id": "ctx_0", "data": [1.0, 2.0]})
        assert response.status_code == 501

    def test_encrypt_unauthenticated(self, client: TestClient):
        """Unauthenticated encrypt requests are rejected."""
        response = client.post("/v1/fhe/encrypt", json={"context_id": "ctx_0", "data": [1.0, 2.0]})
        assert response.status_code == 401

    def test_decrypt_disabled(self, client: TestClient):
        """Decrypt is disabled."""
        _auth_headers(client)
        response = client.post("/v1/fhe/decrypt", json={"encrypted_data": {}})
        assert response.status_code == 501

    def test_add_disabled(self, client: TestClient):
        """Homomorphic add is disabled."""
        _auth_headers(client)
        response = client.post("/v1/fhe/add", json={"context_id": "ctx_0", "encrypted_a": {}, "encrypted_b": {}})
        assert response.status_code == 501

    def test_multiply_disabled(self, client: TestClient):
        """Homomorphic scalar multiplication is disabled."""
        _auth_headers(client)
        response = client.post("/v1/fhe/multiply-scalar", json={"context_id": "ctx_0", "encrypted_a": {}, "scalar": 2.0})
        assert response.status_code == 501

    def test_get_context_info_disabled(self, client: TestClient):
        """Context info is disabled."""
        _auth_headers(client)
        response = client.get("/v1/fhe/context/ctx_0")
        assert response.status_code == 501

    def test_inference_disabled(self, client: TestClient):
        """Encrypted inference is disabled."""
        _auth_headers(client)
        response = client.post("/v1/fhe/inference", json={"context_id": "ctx_0", "encrypted_input": {}, "model": {}})
        assert response.status_code == 501


@pytest.mark.integration
class TestFHEIntegration:
    """Integration tests for FHE workflow — disabled."""

    def test_fhe_workflow_disabled(self, client: TestClient):
        """The full FHE workflow is disabled and returns 501."""
        _auth_headers(client)
        response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        assert response.status_code == 501

        response = client.post("/v1/fhe/encrypt", json={"context_id": "ctx_0", "data": [1.0]})
        assert response.status_code == 501
