"""Retention/memory bound pins for the FHE router (issue #3037).

The FHE router keeps generated contexts and ciphertexts in module-level
stores. Before #3037 those stores were unbounded plain dicts and
``poly_modulus_degree`` was caller-controlled with no ceiling, so any
authenticated client could grow coordinator-api memory without limit.
These tests pin the bounds hermetically against the MockFHEProvider —
no real FHE backend required.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from coordinator_api.contexts.zk_applications.routers import fhe
from coordinator_api.contexts.zk_applications.services.fhe_service import (
    FHEService,
    MockFHEProvider,
)


@pytest.fixture
def fhe_mock(monkeypatch):
    """Point the router at a mock-only FHEService and reset the registries.

    ``FHEService(allow_mock=True)`` can still prefer a real provider as
    default, so the providers map is pinned to mock explicitly. Module
    state is restored after each test.
    """
    service = FHEService(allow_mock=True)
    service.providers = {"mock": MockFHEProvider()}
    service.default_provider = "mock"
    monkeypatch.setattr(fhe, "_service", service)
    fhe._contexts.clear()
    fhe._encrypted.clear()
    yield service
    fhe._contexts.clear()
    fhe._encrypted.clear()


def _auth_headers(client: TestClient) -> None:
    token = create_access_token("test_user", "client")
    client.headers = {"Authorization": f"Bearer {token}"}


def _generate_context(client: TestClient, **overrides) -> dict:
    body = {"scheme": "ckks", **overrides}
    response = client.post("/v1/fhe/context/generate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.unit
class TestPolyModulusDegreeBounds:
    """poly_modulus_degree is bounded to supported ring dimensions."""

    def test_degree_above_max_rejected(self, client: TestClient, fhe_mock):
        """Degrees above the 32768 ceiling are rejected with 4xx."""
        _auth_headers(client)
        response = client.post(
            "/v1/fhe/context/generate",
            json={"scheme": "ckks", "poly_modulus_degree": 65536},
        )
        assert response.status_code == 422

    def test_degree_below_min_rejected(self, client: TestClient, fhe_mock):
        """Degrees below the supported minimum are rejected."""
        _auth_headers(client)
        response = client.post(
            "/v1/fhe/context/generate",
            json={"scheme": "ckks", "poly_modulus_degree": 2048},
        )
        assert response.status_code == 422

    def test_non_power_of_two_rejected(self, client: TestClient, fhe_mock):
        """Ring dimensions must be powers of two for both backends."""
        _auth_headers(client)
        response = client.post(
            "/v1/fhe/context/generate",
            json={"scheme": "ckks", "poly_modulus_degree": 10000},
        )
        assert response.status_code == 422

    def test_supported_degree_accepted(self, client: TestClient, fhe_mock):
        """A supported degree at the ceiling still works."""
        _auth_headers(client)
        context = _generate_context(client, poly_modulus_degree=32768)
        assert context["poly_modulus_degree"] == 32768


@pytest.mark.unit
class TestContextStoreBounds:
    """The context registry is capped, TTL'd, and evicts oldest-first."""

    def test_context_cap_evicts_oldest(self, client: TestClient, fhe_mock, monkeypatch):
        """N+1 contexts evict the least-recently-used entry."""
        monkeypatch.setattr(fhe, "_MAX_CONTEXTS", 3)
        _auth_headers(client)
        ids = [_generate_context(client)["context_id"] for _ in range(3)]

        # Touch the oldest entry so the next insert evicts the second-oldest.
        assert client.get(f"/v1/fhe/context/{ids[0]}").status_code == 200

        newest = _generate_context(client)["context_id"]
        assert len(fhe._contexts) == 3

        assert client.get(f"/v1/fhe/context/{ids[0]}").status_code == 200
        assert client.get(f"/v1/fhe/context/{ids[1]}").status_code == 404
        assert client.get(f"/v1/fhe/context/{ids[2]}").status_code == 200
        assert client.get(f"/v1/fhe/context/{newest}").status_code == 200

    def test_expired_context_is_swept(self, fhe_mock, monkeypatch):
        """Entries past their TTL are dropped on access."""
        monkeypatch.setattr(fhe, "_CONTEXT_TTL_SECONDS", 0.0)
        context = fhe_mock.generate_fhe_context(scheme="ckks")
        fhe._put_context("ctx-expired", context)
        assert fhe._get_context("ctx-expired") is None
        assert "ctx-expired" not in fhe._contexts

    def test_encrypted_cap_evicts_oldest(self, client: TestClient, fhe_mock, monkeypatch):
        """N+1 ciphertexts evict the oldest; the newest still decrypts."""
        monkeypatch.setattr(fhe, "_MAX_ENCRYPTED", 2)
        _auth_headers(client)
        context = _generate_context(client)
        context_id = context["context_id"]

        encrypted_ids = []
        for value in ([1.0], [2.0], [3.0]):
            response = client.post(
                "/v1/fhe/encrypt",
                json={"context_id": context_id, "data": value},
            )
            assert response.status_code == 200
            encrypted_ids.append(response.json()["encrypted_id"])

        assert len(fhe._encrypted) == 2
        assert client.post("/v1/fhe/decrypt", json={"encrypted_id": encrypted_ids[0]}).status_code == 404
        for enc_id in encrypted_ids[1:]:
            response = client.post("/v1/fhe/decrypt", json={"encrypted_id": enc_id})
            assert response.status_code == 200

    def test_expired_ciphertext_is_swept(self, client: TestClient, fhe_mock, monkeypatch):
        """Expired ciphertexts are dropped and report 404."""
        monkeypatch.setattr(fhe, "_ENCRYPTED_TTL_SECONDS", 0.0)
        _auth_headers(client)
        context = _generate_context(client)
        response = client.post(
            "/v1/fhe/encrypt",
            json={"context_id": context["context_id"], "data": [1.0]},
        )
        assert response.status_code == 200
        enc_id = response.json()["encrypted_id"]

        response = client.post("/v1/fhe/decrypt", json={"encrypted_id": enc_id})
        assert response.status_code == 404
        assert enc_id not in fhe._encrypted


@pytest.mark.unit
class TestFHEWorkflowHermetic:
    """generate -> encrypt -> add -> decrypt still works end to end."""

    def test_full_flow_with_mock_provider(self, client: TestClient, fhe_mock):
        _auth_headers(client)
        context = _generate_context(client)

        response = client.post(
            "/v1/fhe/encrypt",
            json={"context_id": context["context_id"], "data": [1.0, 2.0]},
        )
        assert response.status_code == 200
        enc_a = response.json()

        response = client.post(
            "/v1/fhe/encrypt",
            json={"context_id": context["context_id"], "data": [3.0, 4.0]},
        )
        assert response.status_code == 200
        enc_b = response.json()

        response = client.post(
            "/v1/fhe/add",
            json={
                "context_id": context["context_id"],
                "encrypted_a_id": enc_a["encrypted_id"],
                "encrypted_b_id": enc_b["encrypted_id"],
            },
        )
        assert response.status_code == 200
        added = response.json()

        response = client.post("/v1/fhe/decrypt", json={"encrypted_id": added["encrypted_id"]})
        assert response.status_code == 200
        assert response.json()["plaintext"] == pytest.approx([4.0, 6.0])
