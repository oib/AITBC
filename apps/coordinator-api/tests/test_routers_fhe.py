"""
Tests for FHE router (Fully Homomorphic Encryption).

The BFV implementation is disabled; operational endpoints return 501
when authenticated and 401 without authentication. Health remains public.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestFHERouter:
    """Test FHE router endpoints"""

    def test_fhe_health(self, client: TestClient):
        """Health check is public and reports the service as disabled."""
        response = client.get("/v1/fhe/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"
        assert data["fhe_available"] is False
        assert data["service"] == "fhe"

    def test_generate_context_requires_auth(self, client: TestClient):
        """Operational endpoints reject unauthenticated requests."""
        response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv", "poly_modulus_degree": 4096})
        assert response.status_code == 401

    def test_encrypt_requires_auth(self, client: TestClient):
        response = client.post("/v1/fhe/encrypt", json={"context_id": "unused", "data": [1.0]})
        assert response.status_code == 401

    def test_decrypt_requires_auth(self, client: TestClient):
        response = client.post("/v1/fhe/decrypt", json={"encrypted_data": "unused"})
        assert response.status_code == 401

    def test_add_encrypted_requires_auth(self, client: TestClient):
        response = client.post("/v1/fhe/add", json={"context_id": "unused", "encrypted_a": "a", "encrypted_b": "b"})
        assert response.status_code == 401

    def test_multiply_encrypted_requires_auth(self, client: TestClient):
        response = client.post("/v1/fhe/multiply-scalar", json={"context_id": "unused", "encrypted_a": "a", "scalar": 1.0})
        assert response.status_code == 401

    def test_get_context_info_requires_auth(self, client: TestClient):
        response = client.get("/v1/fhe/context/unused")
        assert response.status_code == 401


@pytest.mark.integration
class TestFHEIntegration:
    """Integration tests for the disabled FHE workflow."""

    def test_full_fhe_workflow_rejects_unauthenticated(self, client: TestClient):
        """The first operational step in the workflow now requires authentication."""
        response = client.post("/v1/fhe/context/generate", json={"scheme": "bfv"})
        assert response.status_code == 401
