"""Router tests for /v1/bounty/* (#1289 round 9 batch 5).

bounty_flat is a MOUNTED router whose endpoints return hardcoded
fabricated responses — a real BountyService exists but is never called.
Pinned strict-xfail (#1337): fabricated success on claim/verify/get for
nonexistent bounties, duplicate fixed bounty_id on every create, and an
always-empty list. Contract tests cover health/validation/routing order.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

BASE = "/v1/bounty"


def _create(client: TestClient, **over) -> dict:
    body = {
        "title": "fix the thing",
        "description": "a sufficiently long description",
        "creator": "creator-1",
        "reward": 5000,
    }
    body.update(over)
    return body


class TestBountyStubContract:
    def test_health(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "bounty"

    def test_stats_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/stats")
        assert resp.status_code == 200
        assert "total_bounties" in resp.json()

    def test_routing_order_stats_not_id(self, client: TestClient) -> None:
        # /stats must hit the stats handler, not /{bounty_id} (declaration order pinned)
        resp = client.get(f"{BASE}/stats")
        assert "total_bounties" in resp.json()

    def test_create_validation(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/create", json={}).status_code == 422
        assert client.post(f"{BASE}/create", json=_create(reward=0)).status_code == 422

    def test_list_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/list")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0  # documented: always empty while stubbed


class TestFabricatedResponses:
    @pytest.mark.xfail(
        strict=True,
        reason="#1337: every create returns the same fixed 'bounty-001' — "
        "nothing is persisted; a real BountyService exists but is never called",
    )
    def test_create_returns_unique_persisted_id(self, client: TestClient) -> None:
        r1 = client.post(f"{BASE}/create", json=_create()).json()
        r2 = client.post(f"{BASE}/create", json=_create(title="second")).json()
        assert r1["bounty_id"] != r2["bounty_id"]
        # and the created bounty must be retrievable
        got = client.get(f"{BASE}/{r1['bounty_id']}")
        assert got.status_code == 200
        assert got.json()["title"] == "fix the thing"

    @pytest.mark.xfail(
        strict=True,
        reason="#1337: GET /{bounty_id} returns a fabricated 'Sample Bounty' "
        "for ANY id — real lookups 404 only for the literal 'not-found'",
    )
    def test_get_unknown_bounty_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/bounty-does-not-exist").status_code == 404

    @pytest.mark.xfail(
        strict=True,
        reason="#1337: claim/submit/verify return fabricated success for any "
        "bounty_id — claiming or 'completing' nonexistent bounties succeeds",
    )
    def test_claim_nonexistent_bounty_fails(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/claim", json={"bounty_id": "ghost", "hunter": "h1"})
        assert resp.status_code in (400, 404)

    @pytest.mark.xfail(
        strict=True,
        reason="#1337: verify approves/rejects any bounty_id — payout-affecting "
        "endpoint with fabricated success and no auth dep (matrix ANY)",
    )
    def test_verify_nonexistent_bounty_fails(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/verify",
            json={"bounty_id": "ghost", "verifier": "v1", "approved": True},
        )
        assert resp.status_code in (400, 404)
