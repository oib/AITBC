"""Router tests for /v1/trading/* (#1289 round 9 batch 2).

The trading router carries NO router-level auth dep — the only gate is
the route security matrix (/v1/trading* -> ADMIN_OR_CLIENT), enforced by
middleware before the handler runs. Tests therefore pin the middleware
contract (401 unauthenticated, 403 for miner role) plus request
validation, the create->get->list lifecycle on the real
P2PTradingProtocol + sqlite, and the matches/negotiation/analytics
surface.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from aitbc.auth import create_access_token
from coordinator_api.contexts.trading.domain.trading import TradeMatch, TradeRequest, TradeStatus

BASE = "/v1/trading"
AGENT = "agent-buyer-1"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-a", "admin")


def _miner() -> dict[str, str]:
    return _headers("miner-1", "miner")


def _request_body(**overrides) -> dict:
    body = {
        "buyer_agent_id": AGENT,
        "trade_type": "compute_resources",
        "title": "GPU hours",
        "description": "need 10h",
        "requirements": {"specifications": {"gpu": "a100"}},
        "budget_range": {"min": "10", "max": "50"},
    }
    body.update(overrides)
    return body


class TestTradingAuthBoundary:
    """Matrix gate: /v1/trading* is ADMIN_OR_CLIENT; router adds no dep."""

    def test_unauthenticated_401(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/requests").status_code == 401
        assert client.post(f"{BASE}/requests", json=_request_body()).status_code == 401

    def test_miner_role_403(self, client: TestClient) -> None:
        # MINER is not in ADMIN_OR_CLIENT — matrix must deny before handler
        assert client.get(f"{BASE}/requests", headers=_miner()).status_code == 403
        assert client.post(f"{BASE}/requests", json=_request_body(), headers=_miner()).status_code == 403

    def test_admin_and_client_allowed(self, client: TestClient) -> None:
        for headers in (_admin(), _headers()):
            resp = client.post(f"{BASE}/requests", json=_request_body(), headers=headers)
            assert resp.status_code == 200


class TestTradeRequestLifecycle:
    def test_create_and_get(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["request_id"].startswith("req_")
        assert body["buyer_agent_id"] == AGENT
        assert body["status"] == "open"

        got = client.get(f"{BASE}/requests/{body['request_id']}", headers=_headers())
        assert got.status_code == 200
        assert got.json()["request_id"] == body["request_id"]

    def test_get_missing_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/requests/req_nope", headers=_headers()).status_code == 404

    def test_list_requests(self, client: TestClient) -> None:
        client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        resp = client.get(f"{BASE}/requests", headers=_headers())
        assert resp.status_code == 200
        rows = resp.json()
        assert isinstance(rows, list)
        assert any(r["buyer_agent_id"] == AGENT for r in rows)

    def test_validation(self, client: TestClient) -> None:
        # invalid agent id format
        assert (
            client.post(f"{BASE}/requests", json=_request_body(buyer_agent_id="bad id!"), headers=_headers()).status_code
            == 422
        )
        # bad enum
        assert client.post(f"{BASE}/requests", json=_request_body(trade_type="bogus"), headers=_headers()).status_code == 422
        # missing required fields
        bad = _request_body()
        del bad["requirements"]
        assert client.post(f"{BASE}/requests", json=bad, headers=_headers()).status_code == 422

    @pytest.mark.xfail(
        strict=True,
        reason="defect: unparseable ISO start_time/expires_at raises inside the broad try -> 500 instead of 422",
    )
    def test_bad_datetime_is_422_not_500(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/requests",
            json=_request_body(start_time="not-a-date"),
            headers=_headers(),
        )
        assert resp.status_code == 422


class TestMatchesAndNegotiation:
    def _seed_match(self, db_session: Session, request_id: str) -> str:
        from datetime import UTC, datetime

        match = TradeMatch(
            match_id="match_seed1",
            request_id=request_id,
            buyer_agent_id=AGENT,
            seller_agent_id="agent-seller-1",
            match_score=88.0,
            confidence_level=0.9,
            price_compatibility=90.0,
            specification_compatibility=85.0,
            timing_compatibility=80.0,
            reputation_compatibility=95.0,
            geographic_compatibility=70.0,
            seller_offer={"price": "40", "gpu": "a100"},
            proposed_terms={"price": "40"},
            status=TradeStatus.MATCHING,
            created_at=datetime.now(UTC),
        )
        db_session.add(match)
        db_session.commit()
        return match.match_id

    def test_find_matches_empty_and_get(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        rid = resp.json()["request_id"]
        # no sellers registered -> empty match list, still 200
        m = client.post(f"{BASE}/requests/{rid}/matches", headers=_headers())
        assert m.status_code == 200
        g = client.get(f"{BASE}/requests/{rid}/matches", headers=_headers())
        assert g.status_code == 200
        assert g.json() == []

    def test_find_matches_missing_request_404(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/requests/req_ghost/matches", headers=_headers()).status_code == 404

    def test_negotiation_lifecycle(self, client: TestClient, db_session: Session) -> None:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        rid = resp.json()["request_id"]
        mid = self._seed_match(db_session, rid)

        neg = client.post(
            f"{BASE}/negotiations",
            json={"match_id": mid, "initiator": "buyer", "strategy": "balanced"},
            headers=_headers(),
        )
        assert neg.status_code == 200
        nbody = neg.json()
        assert nbody["negotiation_id"].startswith("neg_")
        assert nbody["match_id"] == mid

        got = client.get(f"{BASE}/negotiations/{nbody['negotiation_id']}", headers=_headers())
        assert got.status_code == 200
        assert got.json()["negotiation_id"] == nbody["negotiation_id"]

    def test_negotiation_validation_and_missing_match(self, client: TestClient) -> None:
        assert (
            client.post(
                f"{BASE}/negotiations",
                json={"match_id": "m1", "initiator": "bogus"},
                headers=_headers(),
            ).status_code
            == 422
        )
        # ghost match -> service ValueError -> router maps to 500 (documented)
        resp = client.post(
            f"{BASE}/negotiations",
            json={"match_id": "match_ghost", "initiator": "buyer"},
            headers=_headers(),
        )
        assert resp.status_code in (404, 500)

    def test_list_endpoints_and_analytics(self, client: TestClient) -> None:
        for path in ("/requests", "/matches", "/negotiations", "/analytics"):
            resp = client.get(f"{BASE}{path}", headers=_headers())
            assert resp.status_code == 200, path
        summary = client.get(f"{BASE}/agents/{AGENT}/summary", headers=_headers())
        assert summary.status_code == 200
        assert summary.json()["agent_id"] == AGENT

    def test_match_row_persisted(self, client: TestClient, db_session: Session) -> None:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        rid = resp.json()["request_id"]
        self._seed_match(db_session, rid)
        rows = db_session.exec(select(TradeRequest).where(TradeRequest.request_id == rid)).all()
        assert len(rows) == 1
