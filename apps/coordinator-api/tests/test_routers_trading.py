"""Router tests for /v1/trading/* (#1289 round 9 batch 2, #1876 authz).

Pre-#1876 the trading router carried NO router-level auth dep — the only
gate was the route security matrix (/v1/trading* -> ADMIN_OR_CLIENT),
enforced by middleware. #1876 added per-handler AdminOrClientDep plus
object-level binding: caller agent ids resolve through
AgentIdentity.owner_address -> wallets owned by the JWT sub. Tests pin
the middleware contract, request validation, the create->get->list
lifecycle, and the cross-user denial surface.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from aitbc.auth import create_access_token
from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import Wallet
from coordinator_api.contexts.trading.domain.trading import TradeMatch, TradeRequest, TradeStatus

BASE = "/v1/trading"
AGENT = "agent-buyer-1"
BUYER_WALLET = "0x2222222222222222222222222222222222222222"
OTHER_WALLET = "0x4a5b3bf95aa06072c568cfcb7392b4e86608b5d2"


@pytest.fixture(autouse=True)
def _bound_buyer_agent(db_session):
    """#1881/#1876: caller agent ids resolve via AgentIdentity.owner_address
    -> wallets owned by the JWT sub. client-1 owns AGENT through
    BUYER_WALLET; client-2 owns a different wallet and no trading agents."""
    db_session.add(Wallet(user_id="client-1", address=BUYER_WALLET))
    db_session.add(Wallet(user_id="client-2", address=OTHER_WALLET))
    db_session.add(AgentIdentity(agent_id=AGENT, owner_address=BUYER_WALLET))
    db_session.commit()


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-a", "admin")


def _other_client() -> dict[str, str]:
    return _headers("client-2", "client")


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
    """The trading router carries NO router-level auth dep — the only gate
    is the route security matrix (/v1/trading* -> ADMIN_OR_CLIENT),
    enforced by AuthMiddleware which is disabled under TEST_MODE. These
    tests pin the matrix contract directly; in production the middleware
    rejects unauthenticated/non-privileged callers before the handler."""

    def test_matrix_requires_admin_or_client(self) -> None:
        from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level

        assert get_auth_level("/v1/trading/requests") == AuthLevel.ADMIN_OR_CLIENT
        assert check_role_match(AuthLevel.ADMIN_OR_CLIENT, "admin")
        assert check_role_match(AuthLevel.ADMIN_OR_CLIENT, "client")
        assert not check_role_match(AuthLevel.ADMIN_OR_CLIENT, "miner")
        assert not check_role_match(AuthLevel.ADMIN_OR_CLIENT, None)

    def test_router_dep_rejects_unauthenticated(self, client: TestClient) -> None:
        # #1876: the router now carries AdminOrClientDep per handler — with
        # TEST_MODE middleware off the dep itself is the gate, so a missing
        # token must 401 before reaching the handler.
        assert client.get(f"{BASE}/requests").status_code == 401


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

    def test_list_requests_limit_bounds(self, client: TestClient) -> None:
        """#1543 (8acafe389): ``limit`` went from ``int | None`` (unbounded
        ``.limit(None)``) to ``Query(default=200, ge=1, le=1000)`` — pin the
        bounds so the unbounded read cannot regress."""
        for bad in ("0", "-1", "1001", "99999", "abc"):
            resp = client.get(f"{BASE}/requests", params={"limit": bad}, headers=_headers())
            assert resp.status_code == 422, f"limit={bad}: {resp.status_code} {resp.text[:120]}"
        for good in ("1", "200", "1000"):
            resp = client.get(f"{BASE}/requests", params={"limit": good}, headers=_headers())
            assert resp.status_code == 200, f"limit={good}: {resp.status_code} {resp.text[:120]}"

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

    def test_get_matches_empty(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        rid = resp.json()["request_id"]
        g = client.get(f"{BASE}/requests/{rid}/matches", headers=_headers())
        assert g.status_code == 200
        assert g.json() == []

    def test_find_matches_runs(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        rid = resp.json()["request_id"]
        # no sellers registered -> empty match list expected, but the
        # persist path 500s on JSON serialization before returning
        m = client.post(f"{BASE}/requests/{rid}/matches", headers=_headers())
        assert m.status_code == 200

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


class TestTradingObjectAuthz1876:
    """#1876 pins: a client JWT may only read/act on trades where it owns a
    party agent (AgentIdentity.owner_address -> caller wallets). Admin
    bypasses; other clients get 403 or scoped-empty lists."""

    def _make_request(self, client: TestClient) -> str:
        resp = client.post(f"{BASE}/requests", json=_request_body(), headers=_headers())
        assert resp.status_code == 200
        return resp.json()["request_id"]

    def _seed_match(self, db_session: Session, request_id: str) -> str:
        from datetime import UTC, datetime

        match = TradeMatch(
            match_id="match_authz1",
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
            seller_offer={"price": "40"},
            proposed_terms={"price": "40"},
            status=TradeStatus.MATCHING,
            created_at=datetime.now(UTC),
        )
        db_session.add(match)
        db_session.commit()
        return match.match_id

    def test_cannot_create_request_as_foreign_agent(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/requests",
            json=_request_body(buyer_agent_id="agent-not-mine"),
            headers=_headers(),
        )
        assert resp.status_code == 403

    def test_cannot_read_foreign_request(self, client: TestClient) -> None:
        rid = self._make_request(client)
        resp = client.get(f"{BASE}/requests/{rid}", headers=_other_client())
        assert resp.status_code == 403
        # admin still reads it
        assert client.get(f"{BASE}/requests/{rid}", headers=_admin()).status_code == 200

    def test_cannot_list_foreign_request_matches(self, client: TestClient, db_session: Session) -> None:
        rid = self._make_request(client)
        self._seed_match(db_session, rid)
        resp = client.get(f"{BASE}/requests/{rid}/matches", headers=_other_client())
        assert resp.status_code == 403
        resp = client.post(f"{BASE}/requests/{rid}/matches", headers=_other_client())
        assert resp.status_code == 403

    def test_cannot_read_foreign_match_or_negotiate(self, client: TestClient, db_session: Session) -> None:
        rid = self._make_request(client)
        mid = self._seed_match(db_session, rid)
        assert client.get(f"{BASE}/matches/{mid}", headers=_other_client()).status_code == 403
        neg = client.post(
            f"{BASE}/negotiations",
            json={"match_id": mid, "initiator": "buyer", "strategy": "balanced"},
            headers=_other_client(),
        )
        assert neg.status_code == 403

    def test_cannot_read_foreign_agent_summary(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/agents/{AGENT}/summary", headers=_other_client())
        assert resp.status_code == 403

    def test_lists_are_scoped_to_caller_agents(self, client: TestClient) -> None:
        self._make_request(client)
        rows = client.get(f"{BASE}/requests", headers=_other_client()).json()
        assert rows == []
        rows = client.get(f"{BASE}/requests", headers=_admin()).json()
        assert any(r["buyer_agent_id"] == AGENT for r in rows)
        # explicit foreign agent_id filter is denied, not silently emptied
        resp = client.get(f"{BASE}/requests", params={"agent_id": AGENT}, headers=_other_client())
        assert resp.status_code == 403

    def test_simulate_requires_owned_agent(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/simulate-match",
            json=_request_body(buyer_agent_id="agent-not-mine"),
            headers=_headers(),
        )
        assert resp.status_code == 403
