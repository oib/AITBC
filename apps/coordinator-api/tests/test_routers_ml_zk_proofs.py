"""Router tests for /v1/ml-zk/* (#1289 round 9 batch 5).

ML ZK-proof endpoints on the real ZKProofService — disabled in tests
(no proving keys), so the pinned contract is honest degradation:
prove -> 503, verify -> service answer or documented 500, circuits
list is static data.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/v1/ml-zk"


def _proof_req() -> dict:
    return {"inputs": {"a": 1}, "private_inputs": {"w": 2}}


def _verify_req() -> dict:
    return {"proof": {"a": "b"}, "public_signals": ["1", "2"]}


class TestMlZkProve:
    def test_prove_training_503_no_keys(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/prove/training", json=_proof_req())
        assert resp.status_code == 503

    def test_prove_modular_503_no_keys(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/prove/modular", json=_proof_req())
        assert resp.status_code == 503

    def test_prove_validation(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/prove/training", json={}).status_code == 422


class TestMlZkVerify:
    def test_verify_training_contract(self, client: TestClient) -> None:
        # disabled service: verify_proof raises -> 500, or returns a dict
        resp = client.post(f"{BASE}/verify/training", json=_verify_req())
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert "verified" in resp.json()

    def test_verify_inference_contract(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/verify/inference", json=_verify_req())
        assert resp.status_code in (200, 500)


class TestCircuits:
    def test_list_circuits(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/circuits")
        assert resp.status_code == 200
        body = resp.json()
        assert "circuits" in body and "count" in body
