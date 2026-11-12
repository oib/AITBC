"""#1881 COORD-OBJ-BIND-MONEY-1 pins: money-path routers bind objects to the
JWT principal, not caller-supplied ids.

Pre-fix: bonds slash/lock/release/create trusted any provider_id; trading
mutations trusted body buyer_agent_id/initiator; confidential key/payment
routes trusted participant_id/sender_id; exchange create-payment fell back
to a body user_id and payment-status was readable by anyone holding the id.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.trading.domain.trading import TradeMatch, TradeRequest, TradeStatus

OWNER_WALLET = "0x3333333333333333333333333333333333333333"
OTHER_WALLET = "0x4444444444444444444444444444444444444444"
AGENT = "agent-buyer-1"


@pytest.fixture(autouse=True)
def _no_payment_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    """monitor_payment is an infinite background loop — no-op it like
    test_routers_exchange does."""
    import coordinator_api.contexts.infrastructure.routers.exchange as exch_mod

    async def _noop(payment_id: str) -> None:
        return None

    monkeypatch.setattr(exch_mod, "monitor_payment", _noop)


def _headers(user_id: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
def seeded(db_session):
    db_session.add(User(id="owner1", email="o@x", username="owner1"))
    db_session.add(Wallet(user_id="owner1", address=OWNER_WALLET))
    db_session.add(User(id="intruder", email="i@x", username="intruder"))
    db_session.add(Wallet(user_id="intruder", address=OTHER_WALLET))
    db_session.add(Miner(id="miner-1", capabilities={"wallet_address": OWNER_WALLET}))
    db_session.add(AgentIdentity(agent_id=AGENT, owner_address=OWNER_WALLET))
    db_session.commit()


def _trade_body(**over) -> dict:
    body = {
        "buyer_agent_id": AGENT,
        "trade_type": "compute_resources",
        "title": "GPU hours",
        "requirements": {"specifications": {"gpu": "a100"}},
        "budget_range": {"min": "10", "max": "50"},
    }
    body.update(over)
    return body


# --- bonds ---


class TestBondObjectBinding:
    def test_intruder_cannot_create_bond(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/market/providers/miner-1/bonds",
            json={"amount": "5"},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_intruder_cannot_slash(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/market/providers/miner-1/bonds/slash",
            json={"reason": "fraud"},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_owner_via_miner_wallet_can_create(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/market/providers/miner-1/bonds",
            json={"amount": "5"},
            headers=_headers("owner1"),
        )
        assert resp.status_code == 200

    def test_miner_sub_can_lock_own_bond(self, client: TestClient, seeded) -> None:
        client.post("/v1/market/providers/miner-1/bonds", json={"amount": "5"}, headers=_headers("owner1"))
        resp = client.post("/v1/market/providers/miner-1/bonds/lock", headers=_headers("miner-1", "miner"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"

    def test_admin_can_slash_any_provider(self, client: TestClient, seeded) -> None:
        client.post("/v1/market/providers/miner-1/bonds", json={"amount": "5"}, headers=_headers("owner1"))
        resp = client.post(
            "/v1/market/providers/miner-1/bonds/slash",
            json={"reason": "fraud"},
            headers=_headers("admin-a", "admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "liquidated"

    def test_reads_stay_authenticated_not_bound(self, client: TestClient, seeded) -> None:
        # eligibility/bond reads are needed by job matching — any valid
        # principal may read them (#1881 binds mutations only).
        assert client.get("/v1/market/providers/miner-1/eligibility", headers=_headers("intruder")).status_code == 200


# --- exchange ---


class TestExchangeObjectBinding:
    def _create(self, client: TestClient, sub: str = "u") -> dict:
        resp = client.post(
            "/v1/exchange/create-payment",
            json={"user_id": "someone-else", "aitbc_amount": "1000", "eth_amount": "1"},
            headers=_headers(sub),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_create_binds_token_sub_not_body(self, client: TestClient, seeded) -> None:
        body = self._create(client, "u")
        assert body["user_id"] == "u"

    def test_status_foreign_payment_403(self, client: TestClient, seeded) -> None:
        payment = self._create(client, "u")
        resp = client.get(f"/v1/exchange/payment-status/{payment['payment_id']}", headers=_headers("intruder"))
        assert resp.status_code == 403

    def test_status_owner_and_admin_ok(self, client: TestClient, seeded) -> None:
        payment = self._create(client, "u")
        pid = payment["payment_id"]
        assert client.get(f"/v1/exchange/payment-status/{pid}", headers=_headers("u")).status_code == 200
        assert client.get(f"/v1/exchange/payment-status/{pid}", headers=_headers("admin-a", "admin")).status_code == 200

    def test_status_unauthenticated_401(self, client: TestClient, seeded) -> None:
        payment = self._create(client, "u")
        assert client.get(f"/v1/exchange/payment-status/{payment['payment_id']}").status_code == 401


# --- confidential ---


class TestConfidentialObjectBinding:
    def test_register_foreign_participant_403(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/confidential/keys/register",
            json={"participant_id": "intruder", "public_key": "AAAA", "algorithm": "X25519"},
            headers=_headers("owner1"),
        )
        assert resp.status_code == 403

    def test_rotate_foreign_participant_403(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/confidential/keys/rotate",
            params={"participant_id": "intruder"},
            headers=_headers("owner1"),
        )
        assert resp.status_code == 403

    def test_payment_foreign_sender_403(self, client: TestClient, seeded, monkeypatch) -> None:
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "confidential_tee_enabled", True)
        resp = client.post(
            "/v1/confidential/payments",
            json={
                "payment_id": "pay-1",
                "sender_id": "intruder",
                "recipient_id": "recipient-1",
                "amount_commitment": "0x01",
            },
            headers=_headers("owner1"),
        )
        assert resp.status_code == 403

    def test_admin_may_act_for_any_participant(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/confidential/keys/rotate",
            params={"participant_id": "intruder"},
            headers=_headers("admin-a", "admin"),
        )
        # admin passes the binding; downstream key ops may still fail, but not 403
        assert resp.status_code != 403


# --- trading ---


class TestTradingObjectBinding:
    def test_create_unowned_agent_403(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/trading/requests",
            json=_trade_body(buyer_agent_id="agent-not-mine"),
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_create_owned_agent_ok(self, client: TestClient, seeded) -> None:
        resp = client.post("/v1/trading/requests", json=_trade_body(), headers=_headers("owner1"))
        assert resp.status_code == 200, resp.text

    def test_find_matches_binds_request_owner(self, client: TestClient, db_session, seeded) -> None:

        req = TradeRequest(
            request_id="req_foreign",
            buyer_agent_id="agent-not-mine",
            trade_type="compute_resources",
            title="t",
            requirements={},
            budget_range={"min": "1", "max": "2"},
        )
        db_session.add(req)
        db_session.commit()
        resp = client.post("/v1/trading/requests/req_foreign/matches", headers=_headers("intruder"))
        assert resp.status_code == 403

    def test_negotiation_binds_initiator_side(self, client: TestClient, db_session, seeded) -> None:
        from datetime import UTC, datetime

        match = TradeMatch(
            match_id="match_x",
            request_id="req_x",
            buyer_agent_id="agent-not-mine",
            seller_agent_id="agent-seller-1",
            match_score=1.0,
            confidence_level=0.5,
            price_compatibility=1.0,
            specification_compatibility=1.0,
            timing_compatibility=1.0,
            reputation_compatibility=1.0,
            geographic_compatibility=1.0,
            seller_offer={},
            proposed_terms={},
            status=TradeStatus.MATCHING,
            created_at=datetime.now(UTC),
        )
        db_session.add(match)
        db_session.commit()
        # intruder owns neither side
        resp = client.post(
            "/v1/trading/negotiations",
            json={"match_id": "match_x", "initiator": "buyer", "strategy": "balanced"},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403
        # seller-initiated also bound to seller agent
        resp = client.post(
            "/v1/trading/negotiations",
            json={"match_id": "match_x", "initiator": "seller", "strategy": "balanced"},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_admin_bypasses_agent_binding(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/trading/requests",
            json=_trade_body(buyer_agent_id="agent-not-mine"),
            headers=_headers("admin-a", "admin"),
        )
        assert resp.status_code == 200, resp.text
