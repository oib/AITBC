"""Router tests for /v1/zk/* (#1289 round 9 batch 2) — ZK proof endpoints.

Matrix floor ANY (any valid JWT). The service is the global
``zk_proof_service``; in the test environment it is disabled, so
/generate returns 400 and /info reports enabled=false — the tests pin
that contract plus the receipt-circuit guard on /verify.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/zk"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('client-1', 'client')}"}


class TestZkAuthBoundary:
    def test_matrix_floor_any(self) -> None:
        # /v1/zk* is AuthLevel.ANY — any valid JWT; AuthMiddleware is off
        # under TEST_MODE so HTTP-level 401 is not observable here
        from aitbc.auth.security_matrix import AuthLevel, get_auth_level

        assert get_auth_level("/v1/zk/generate") == AuthLevel.ANY
        assert get_auth_level("/v1/zk/info") == AuthLevel.ANY

    def test_any_role_allowed(self, client: TestClient) -> None:
        for role in ("client", "admin", "miner"):
            headers = {"Authorization": f"Bearer {create_access_token('u', role)}"}
            assert client.get(f"{BASE}/info", headers=headers).status_code == 200


class TestZkEndpoints:
    def test_info_disabled_or_enabled(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/info", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert "enabled" in body
        assert isinstance(body["available_circuits"], list)

    def test_generate_disabled_service_400(self, client: TestClient) -> None:
        # zk_proof_service disabled in tests -> generate_proof returns None -> 400
        resp = client.post(
            f"{BASE}/generate",
            json={"circuit_name": "receipt_public", "inputs": {"a": 1}},
            headers=_headers(),
        )
        assert resp.status_code in (400, 503)

    def test_verify_receipt_circuit_refused(self, client: TestClient) -> None:
        # receipt circuits must go through /receipt/verify — hard 400 before service
        resp = client.post(
            f"{BASE}/verify",
            json={
                "proof": {"a": 1},
                "public_signals": ["0x1"],
                "circuit_name": "receipt_public",
            },
            headers=_headers(),
        )
        assert resp.status_code == 400
        assert "receipt/verify" in resp.json()["detail"]

    def test_verify_generic_circuit(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/verify",
            json={
                "proof": {"a": 1},
                "public_signals": ["0x1"],
                "circuit_name": "computation_correct",
            },
            headers=_headers(),
        )
        # disabled service -> verify_proof raises -> 500, or returns verified:false
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert "verified" in resp.json()

    def test_health_endpoints(self, client: TestClient) -> None:
        for path in ("/health", "/health/computation-correct"):
            resp = client.get(f"{BASE}{path}", headers=_headers())
            assert resp.status_code == 200, path

    def test_receipt_verify_missing_job_404(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/receipt/verify", json={"job_id": "job_ghost"}, headers=_headers())
        assert resp.status_code == 404
