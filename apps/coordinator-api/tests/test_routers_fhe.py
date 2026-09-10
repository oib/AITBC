"""Tests for FHE router (Fully Homomorphic Encryption)."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from coordinator_api.contexts.zk_applications.services.fhe_service import FHEService


def _auth_headers(client: TestClient) -> None:
    """Attach a valid JWT to the test client for FHE routes."""
    token = create_access_token("test_user", "client")
    client.headers = {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def fhe_available() -> bool:
    """Return whether the default FHE provider (TenSEAL) is available."""
    return FHEService().get_provider().available


@pytest.mark.unit
class TestFHERouter:
    """Test FHE router endpoints are protected and functional when available."""

    def test_fhe_health_requires_auth(self, client: TestClient):
        """FHE health endpoint requires authentication."""
        response = client.get("/v1/fhe/health")
        assert response.status_code == 401

    def test_fhe_health(self, client: TestClient, fhe_available: bool):
        """FHE health endpoint reports availability when authenticated."""
        _auth_headers(client)
        response = client.get("/v1/fhe/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ("available" if fhe_available else "unavailable")
        assert data["fhe_available"] == fhe_available
        assert data["service"] == "fhe"

    def test_unauthenticated_encrypt_rejected(self, client: TestClient):
        """Unauthenticated encrypt requests are rejected."""
        response = client.post("/v1/fhe/encrypt", json={"context_id": "ctx_0", "data": [1.0, 2.0]})
        assert response.status_code == 401

    def test_fhe_workflow(self, client: TestClient, fhe_available: bool):
        """The full FHE workflow succeeds when a provider is available."""
        _auth_headers(client)
        if not fhe_available:
            response = client.post("/v1/fhe/context/generate", json={"scheme": "ckks"})
            assert response.status_code == 503
            return

        response = client.post("/v1/fhe/context/generate", json={"scheme": "ckks"})
        assert response.status_code == 200
        context = response.json()
        assert context["scheme"] == "ckks"
        assert context["context_id"]

        response = client.post(
            "/v1/fhe/encrypt",
            json={"context_id": context["context_id"], "data": [1.0, 2.0, 3.0]},
        )
        assert response.status_code == 200
        encrypted_a = response.json()
        assert "encrypted_id" in encrypted_a
        assert "ciphertext_b64" in encrypted_a
        assert base64.b64decode(encrypted_a["ciphertext_b64"])

        response = client.post("/v1/fhe/decrypt", json={"encrypted_id": encrypted_a["encrypted_id"]})
        assert response.status_code == 200
        assert response.json()["plaintext"] == pytest.approx([1.0, 2.0, 3.0], rel=1e-3)

        response = client.post(
            "/v1/fhe/encrypt",
            json={"context_id": context["context_id"], "data": [4.0, 5.0, 6.0]},
        )
        assert response.status_code == 200
        encrypted_b = response.json()

        response = client.post(
            "/v1/fhe/add",
            json={
                "context_id": context["context_id"],
                "encrypted_a_id": encrypted_a["encrypted_id"],
                "encrypted_b_id": encrypted_b["encrypted_id"],
            },
        )
        assert response.status_code == 200
        added = response.json()

        response = client.post("/v1/fhe/decrypt", json={"encrypted_id": added["encrypted_id"]})
        assert response.status_code == 200
        assert response.json()["plaintext"] == pytest.approx([5.0, 7.0, 9.0], rel=1e-3)

        response = client.post(
            "/v1/fhe/multiply-scalar",
            json={
                "context_id": context["context_id"],
                "encrypted_a_id": encrypted_a["encrypted_id"],
                "scalar": 2.0,
            },
        )
        assert response.status_code == 200
        multiplied = response.json()

        response = client.post("/v1/fhe/decrypt", json={"encrypted_id": multiplied["encrypted_id"]})
        assert response.status_code == 200
        assert response.json()["plaintext"] == pytest.approx([2.0, 4.0, 6.0], rel=1e-3)

        response = client.get(f"/v1/fhe/context/{context['context_id']}")
        assert response.status_code == 200
        assert response.json()["context_id"] == context["context_id"]


@pytest.mark.integration
class TestFHEIntegration:
    """Integration tests for FHE workflow."""

    def test_fhe_workflow(self, client: TestClient, fhe_available: bool):
        """The full FHE workflow succeeds when a provider is available."""
        _auth_headers(client)
        if not fhe_available:
            response = client.post("/v1/fhe/context/generate", json={"scheme": "ckks"})
            assert response.status_code == 503
            return

        response = client.post("/v1/fhe/context/generate", json={"scheme": "ckks"})
        assert response.status_code == 200
        context = response.json()

        response = client.post(
            "/v1/fhe/encrypt",
            json={"context_id": context["context_id"], "data": [1.0, 1.0]},
        )
        assert response.status_code == 200
        encrypted = response.json()

        response = client.post(
            "/v1/fhe/inference",
            json={
                "context_id": context["context_id"],
                "encrypted_input_id": encrypted["encrypted_id"],
                "model": {"weights": [0.5, 0.5], "biases": [0.0]},
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert "encrypted_id" in result

        response = client.post("/v1/fhe/decrypt", json={"encrypted_id": result["encrypted_id"]})
        assert response.status_code == 200
        assert response.json()["plaintext"] == pytest.approx([1.0], rel=1e-2)


@pytest.mark.unit
class TestFHEFailClosed:
    """Fail-closed behavior when no real provider is available."""

    def _service_with_no_provider(self) -> FHEService:
        """Return an FHEService with no registered providers."""
        service = FHEService(allow_mock=False)
        service.providers.clear()
        service.default_provider = None
        return service

    def test_context_generate_returns_503_without_provider(self, client: TestClient):
        """FHE endpoints return 503 when the default provider is missing."""
        from coordinator_api.contexts.zk_applications.routers import fhe

        _auth_headers(client)
        original_service = fhe._service
        fhe._service = self._service_with_no_provider()
        try:
            response = client.post("/v1/fhe/context/generate", json={"scheme": "ckks"})
            assert response.status_code == 503
        finally:
            fhe._service = original_service

    def test_fhe_health_unavailable_without_provider(self, client: TestClient):
        """Health endpoint reports unavailable when no provider is active."""
        from coordinator_api.contexts.zk_applications.routers import fhe

        _auth_headers(client)
        original_service = fhe._service
        fhe._service = self._service_with_no_provider()
        try:
            response = client.get("/v1/fhe/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unavailable"
            assert data["fhe_available"] is False
        finally:
            fhe._service = original_service
