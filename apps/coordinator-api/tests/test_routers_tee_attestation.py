"""Router tests for /v1/tee/* (#1289 round 9 batch 2) — TEE attestation.

Matrix floor is AuthLevel.ANY for /v1/tee*; enclave registration adds
router-level AuthDep + caller-derived ownership (the 2026-08-24 fix:
client-supplied agent_id is ignored, ownership = user["sub"], and
register_enclave refuses to reassign an existing enclave). Attestation
submit is gated by settings.tee_attestation_enabled (default False ->
fail-closed 503).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/tee"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _enclave_body(**overrides) -> dict:
    body = {
        "enclave_id": "enc-1",
        "public_key": "0xpubkey",
        "agent_id": "spoofed-agent",  # must be ignored — ownership is caller-derived
        "status": "active",
        "allowed_measurements": ["m1"],
    }
    body.update(overrides)
    return body


class TestAttestationSubmitGate:
    def test_submit_503_when_disabled(self, client: TestClient) -> None:
        # default settings: tee_attestation_enabled=False (fail-closed)
        resp = client.post(
            f"{BASE}/attestations",
            json={"enclave_id": "e", "quote": "q"},
            headers=_headers(),
        )
        assert resp.status_code == 503

    def test_submit_matrix_floor_any(self) -> None:
        # /v1/tee* is AuthLevel.ANY — any valid JWT reaches the handler;
        # with TEST_MODE the middleware is off so the 503 gate fires first
        from aitbc.auth.security_matrix import AuthLevel, get_auth_level

        assert get_auth_level("/v1/tee/attestations") == AuthLevel.ANY


class TestEnclaveRegistry:
    def test_register_requires_auth(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/enclaves", json=_enclave_body()).status_code == 401

    def test_register_and_get(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/enclaves", json=_enclave_body(), headers=_headers())
        assert resp.status_code == 201
        body = resp.json()
        assert body["enclave_id"] == "enc-1"
        # ownership must be the caller sub, NOT the spoofed agent_id
        assert body["agent_id"] == "client-1"

        got = client.get(f"{BASE}/enclaves/enc-1", headers=_headers())
        assert got.status_code == 200
        assert got.json()["enclave_id"] == "enc-1"

    def test_get_missing_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/enclaves/ghost", headers=_headers()).status_code == 404

    def test_invalid_status_400(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/enclaves",
            json=_enclave_body(status="bogus"),
            headers=_headers(),
        )
        assert resp.status_code == 400

    def test_ownership_not_reassignable(self, client: TestClient) -> None:
        client.post(f"{BASE}/enclaves", json=_enclave_body(), headers=_headers("client-1"))
        # a different caller cannot take over the enclave_id
        resp = client.post(
            f"{BASE}/enclaves",
            json=_enclave_body(public_key="0xother"),
            headers=_headers("client-2"),
        )
        assert resp.status_code == 403


class TestAttestationRead:
    def test_get_attestation_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/attestations/att_nope", headers=_headers()).status_code == 404
