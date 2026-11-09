"""Router tests for /v1/zk/* (#1289 round 9 batch 5).

zk_applications router — mixed real/demo surface. Demo-gated endpoints
honestly 503 (DEMO_MODE_ENABLED=False). Two fabricated-behavior defects
pinned (#1336): /zk/receipt/attest returns verified:true unconditionally
with no auth and no demo gate; /zk/anonymity/sets reports hardcoded
fictional set sizes as fact.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

BASE = "/v1/zk"


class TestDemoGatedEndpoints:
    @pytest.mark.parametrize(
        "method,path,json_body",
        [
            ("post", "/zk/membership/verify", {"group_id": "miners", "nullifier": "n1", "proof": "x" * 30}),
            ("post", "/zk/market/private-bid", {"bid_commitment": "0x" + "ab" * 32, "proof": "p" * 30}),
            (
                "post",
                "/zk/computation/verify",
                {"job_id": "j1", "proof_of_execution": "x" * 30, "result_hash": "h", "public_inputs": {}},
            ),
            ("post", "/zk/stealth/address", None),
        ],
    )
    def test_demo_gate_503(self, client: TestClient, method: str, path: str, json_body) -> None:
        kwargs = {"params": {"recipient_public_key": "0x" + "cd" * 32}} if path.endswith("stealth/address") else {}
        if json_body is not None:
            kwargs["json"] = json_body
        resp = getattr(client, method)(f"{BASE}{path}", **kwargs)
        assert resp.status_code == 503


class TestIdentityCommitment:
    def test_commit_shape(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/identity/commit",
            json={"email": "dev@example.com", "user_id": "u1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["commitment"]) == 64  # sha256 hex
        assert body["salt"]
        # hash commitment is deterministic for same input+salt
        assert body["user_id"] == "u1"


class TestStatus:
    def test_zk_status_honest(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["zk_features"]["trusted_setup"] == "development-only"
        assert "circuit_status" in body


class TestFabricatedSurfaces:
    @pytest.mark.xfail(
        strict=True,
        reason="#1336: /zk/receipt/attest returns verified:true unconditionally — "
        "no proof check, no auth dep, no demo gate; fabricated attestation in production",
    )
    def test_receipt_attest_does_not_claim_verified(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/receipt/attest",
            params={"job_id": "j1", "user_address": "0x" + "11" * 20, "computation_result": "r"},
        )
        assert resp.status_code == 200
        assert resp.json().get("verified") is not True

    @pytest.mark.xfail(
        strict=True,
        reason="#1336: /zk/anonymity/sets reports hardcoded fictional set sizes "
        "(100/500/1000) as fact — no backing data source",
    )
    def test_anonymity_sets_not_fabricated(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/anonymity/sets")
        assert resp.status_code == 200
        body = resp.json()
        # a real implementation must source these from the chain/state, not literals
        assert body.get("source") or body.get("generated_at") or "unavailable" in str(body).lower()
