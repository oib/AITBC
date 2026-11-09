"""Router tests for the deliberately-unmounted zk_applications router (#1289 round 9 batch 5).

`contexts/zk_applications/routers/zk_applications.py` is imported in
`routers/__init__.py` for the module contract but is NEVER
`include_router`'d in main.py (documented there: "the mounted ZK surface
is zk_proofs / ml_zk_proofs / fhe"). The mounted `/v1/zk/*` namespace
belongs to `zk_proofs.py` (generate/verify/info/receipt/verify/health).

Coverage therefore pins the unmounted contract: every zk_applications
endpoint path must 404 through the app — same pattern as the swarm
stub. The fabricated-surface findings in that module (receipt attest
verified:true, fictional anonymity sets) are LATENT, not
production-reachable; tracked on #1336 pending an AD mount-or-delete
decision.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

BASE = "/v1/zk"

#: Every route declared in zk_applications.py — all must 404 while unmounted.
ZK_APP_PATHS = [
    ("post", "/identity/commit", {"email": "d@x.com", "user_id": "u1"}),
    ("post", "/membership/verify", {"group_id": "miners", "nullifier": "n", "proof": "x" * 30}),
    ("post", "/market/private-bid", {"bid_commitment": "0x" + "ab" * 32, "proof": "p" * 30}),
    (
        "post",
        "/computation/verify",
        {"job_id": "j1", "proof_of_execution": "x" * 30, "result_hash": "h", "public_inputs": {}},
    ),
    ("post", "/receipt/attest", None),
    ("get", "/anonymity/sets", None),
    ("post", "/stealth/address", None),
    ("get", "/status", None),
]


class TestUnmountedContract:
    @pytest.mark.parametrize("method,path,json_body", ZK_APP_PATHS)
    def test_zk_applications_paths_404(self, client: TestClient, method: str, path: str, json_body) -> None:
        kwargs: dict = {}
        if method == "post" and path == "/receipt/attest":
            kwargs["params"] = {"job_id": "j1", "user_address": "0x" + "11" * 20}
        elif method == "post" and path == "/stealth/address":
            kwargs["params"] = {"recipient_public_key": "0x" + "cd" * 32}
        elif json_body is not None:
            kwargs["json"] = json_body
        resp = getattr(client, method)(f"{BASE}{path}", **kwargs)
        assert resp.status_code == 404, f"{method.upper()} {BASE}{path} -> {resp.status_code}"

    def test_mounted_zk_namespace_still_serves_zk_proofs(self, client: TestClient) -> None:
        # the /v1/zk prefix itself is live via zk_proofs.py — unmounting
        # zk_applications must not have taken the whole namespace down
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200
