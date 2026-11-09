"""Router tests for /v1/bounty/* (#1289 round 9 batch 5; #1337 fix).

bounty_flat is a MOUNTED router (matrix ANY). #1337 replaced the
fabricated responses: reads now hit the real BountyService + DB;
mutations are honest 501s (flat contract can't express
BountyService.create_bounty's required fields, and the service has no
claim step or payment integration). Tests seed real Bounty rows via
db_session and verify round-trip reads, 404s, status filtering, and
the 501 mutation contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from coordinator_api.contexts.bounty.domain.bounty import Bounty, BountyStatus

BASE = "/v1/bounty"


def _seed_bounty(
    db_session: Session, *, bounty_id: str = "bounty_test1", status: BountyStatus = BountyStatus.ACTIVE
) -> Bounty:
    bounty = Bounty(
        bounty_id=bounty_id,
        title="fix the thing",
        description="a sufficiently long description",
        reward_amount=Decimal("50.0"),
        creator_id="creator-1",
        status=status,
        deadline=datetime.now(UTC) + timedelta(days=7),
        tags=["python", "bugfix"],
    )
    db_session.add(bounty)
    db_session.commit()
    return bounty


def _create_body(**over) -> dict:
    body = {
        "title": "fix the thing",
        "description": "a sufficiently long description",
        "creator": "creator-1",
        "reward": 5000,
    }
    body.update(over)
    return body


class TestBountyReads:
    def test_health_real_count(self, client: TestClient, db_session: Session) -> None:
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "bounty"
        assert body["total_bounties"] == 0
        _seed_bounty(db_session)
        assert client.get(f"{BASE}/health").json()["total_bounties"] == 1

    def test_list_empty_then_seeded(self, client: TestClient, db_session: Session) -> None:
        resp = client.get(f"{BASE}/list")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        _seed_bounty(db_session)
        resp = client.get(f"{BASE}/list")
        body = resp.json()
        assert body["count"] == 1
        assert body["bounties"][0]["bounty_id"] == "bounty_test1"
        assert body["bounties"][0]["title"] == "fix the thing"

    def test_list_status_filter(self, client: TestClient, db_session: Session) -> None:
        _seed_bounty(db_session, bounty_id="b-active", status=BountyStatus.ACTIVE)
        _seed_bounty(db_session, bounty_id="b-done", status=BountyStatus.COMPLETED)
        resp = client.get(f"{BASE}/list", params={"status": "completed"})
        assert resp.status_code == 200
        ids = [b["bounty_id"] for b in resp.json()["bounties"]]
        assert ids == ["b-done"]

    def test_list_invalid_status_400(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/list", params={"status": "bogus"})
        assert resp.status_code == 400

    def test_list_tag_filter(self, client: TestClient, db_session: Session) -> None:
        _seed_bounty(db_session)
        resp = client.get(f"{BASE}/list", params={"tag": "python"})
        assert resp.json()["count"] == 1
        resp = client.get(f"{BASE}/list", params={"tag": "rust"})
        assert resp.json()["count"] == 0

    def test_stats_real_aggregates(self, client: TestClient, db_session: Session) -> None:
        _seed_bounty(db_session, status=BountyStatus.ACTIVE)
        _seed_bounty(db_session, bounty_id="b2", status=BountyStatus.COMPLETED)
        resp = client.get(f"{BASE}/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_bounties"] == 2
        assert body["open_bounties"] == 1
        assert body["completed_bounties"] == 1
        assert body["total_reward"] == "50.0"
        assert "success_rate" in body and "tier_distribution" in body

    def test_routing_order_stats_not_id(self, client: TestClient) -> None:
        # /stats must hit the stats handler, not /{bounty_id} (declaration order pinned)
        resp = client.get(f"{BASE}/stats")
        assert "total_bounties" in resp.json()

    def test_get_bounty_roundtrip(self, client: TestClient, db_session: Session) -> None:
        _seed_bounty(db_session)
        resp = client.get(f"{BASE}/bounty_test1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "fix the thing"
        assert body["creator_id"] == "creator-1"
        assert Decimal(str(body["reward_amount"])) == Decimal("50.0")

    def test_get_unknown_bounty_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/bounty-does-not-exist").status_code == 404


class TestBountyMutationsHonest501:
    def test_create_validation_still_applies(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/create", json={}).status_code == 422
        assert client.post(f"{BASE}/create", json=_create_body(reward=0)).status_code == 422

    @pytest.mark.parametrize(
        "path,body",
        [
            ("create", _create_body()),
            ("claim", {"bounty_id": "b1", "hunter": "h1"}),
            ("submit", {"bounty_id": "b1", "hunter": "h1", "solution_url": "https://x/s"}),
            ("verify", {"bounty_id": "b1", "verifier": "v1", "approved": True}),
        ],
    )
    def test_mutations_501_not_fabricated(self, client: TestClient, path: str, body: dict) -> None:
        # #1337: no fabricated success — honest not-implemented, and nothing persisted
        resp = client.post(f"{BASE}/{path}", json=body)
        assert resp.status_code == 501
        assert "not implemented" in resp.json()["detail"].lower()

    def test_verify_does_not_fake_payout(self, client: TestClient, db_session: Session) -> None:
        _seed_bounty(db_session)
        resp = client.post(f"{BASE}/verify", json={"bounty_id": "bounty_test1", "verifier": "v1", "approved": True})
        assert resp.status_code == 501
        # the seeded bounty must be untouched
        got = client.get(f"{BASE}/bounty_test1").json()
        assert got["status"] == "active"
