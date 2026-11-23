"""#2697: portfolio endpoints must not be a confused deputy for the wallet admin key.

Non-admin callers only see wallets their identity controls (sub + registered
Wallet rows); admin keeps the unfiltered view; an explicit foreign
agent_address is a 403. Wallet-service error strings must not leak into the
response.
"""

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

from coordinator_api.contexts.infrastructure.domain.user import Wallet
from coordinator_api.contexts.portfolio.routers.portfolio import portfolio_service

OWNER_SUB = "owner-2697"
OWNER_WALLET = "0x" + "aa" * 20
FOREIGN_WALLET = "0x" + "bb" * 20


def _headers(sub: str = OWNER_SUB, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _portfolio_payload() -> dict:
    return {
        "timestamp": "2026-11-23T00:00:00+00:00",
        "agent_address": None,
        "wallet": {"wallets": [], "total_wallets": 0, "total_balance": 0},
        "exchange": {},
        "market": {},
        "trading": {},
        "ai_signals": {},
        "summary": {},
    }


@pytest.fixture
def captured(monkeypatch):
    calls: list[dict] = []

    async def fake_get_unified(agent_address=None, allowed_addresses=None):
        calls.append({"agent_address": agent_address, "allowed_addresses": allowed_addresses})
        return _portfolio_payload()

    monkeypatch.setattr(portfolio_service, "get_unified_portfolio", fake_get_unified)
    return calls


@pytest.mark.unit
class TestPortfolioWalletScope:
    def test_client_sees_only_own_wallets(self, client: TestClient, db_session, captured) -> None:
        db_session.add(Wallet(user_id=OWNER_SUB, address=OWNER_WALLET))
        db_session.add(Wallet(user_id="someone-else", address=FOREIGN_WALLET))
        db_session.commit()

        resp = client.get("/v1/portfolio/unified", headers=_headers())
        assert resp.status_code == 200, resp.text
        assert len(captured) == 1
        allowed = captured[0]["allowed_addresses"]
        assert allowed is not None
        assert OWNER_WALLET.lower() in allowed
        assert FOREIGN_WALLET.lower() not in allowed
        # sub itself is an identity even without a Wallet row
        assert OWNER_SUB.lower() in allowed

    def test_client_foreign_agent_address_is_403(self, client: TestClient, db_session, captured) -> None:
        db_session.add(Wallet(user_id=OWNER_SUB, address=OWNER_WALLET))
        db_session.commit()
        resp = client.get(f"/v1/portfolio/unified?agent_address={FOREIGN_WALLET}", headers=_headers())
        assert resp.status_code == 403
        assert captured == []

    def test_client_own_agent_address_passes(self, client: TestClient, db_session, captured) -> None:
        db_session.add(Wallet(user_id=OWNER_SUB, address=OWNER_WALLET))
        db_session.commit()
        resp = client.get(f"/v1/portfolio/unified?agent_address={OWNER_WALLET}", headers=_headers())
        assert resp.status_code == 200, resp.text
        assert captured[0]["agent_address"] == OWNER_WALLET

    def test_admin_unfiltered(self, client: TestClient, db_session, captured) -> None:
        resp = client.get("/v1/portfolio/unified", headers=_headers(sub="admin1", role="admin"))
        assert resp.status_code == 200, resp.text
        assert captured[0]["allowed_addresses"] is None

    def test_summary_route_scoped_too(self, client: TestClient, db_session, captured) -> None:
        db_session.add(Wallet(user_id=OWNER_SUB, address=OWNER_WALLET))
        db_session.commit()
        resp = client.get("/v1/portfolio/summary", headers=_headers())
        assert resp.status_code == 200, resp.text
        assert captured[0]["allowed_addresses"] is not None
        assert FOREIGN_WALLET.lower() not in captured[0]["allowed_addresses"]

    def test_unauthenticated_rejected(self, client: TestClient) -> None:
        resp = client.get("/v1/portfolio/unified")
        assert resp.status_code in (401, 403)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, wallets):
        self._wallets = wallets

    async def get(self, url, headers=None):
        if url.endswith("/v1/wallets"):
            return _FakeResponse({"items": self._wallets})
        return _FakeResponse({"balance": 0})


@pytest.mark.unit
class TestWalletBalanceFiltering:
    @pytest.mark.asyncio
    async def test_allowed_addresses_filters_wallet_list(self) -> None:
        from coordinator_api.contexts.portfolio.services.portfolio_aggregation_service import (
            PortfolioAggregationService,
        )

        svc = PortfolioAggregationService()
        svc.http_client = _FakeClient(
            [
                {"wallet_id": "w1", "address": OWNER_WALLET, "public_key": "pk1"},
                {"wallet_id": "w2", "address": FOREIGN_WALLET, "public_key": "pk2"},
                {"wallet_id": "w3", "address": None, "public_key": "unmatched"},
            ]
        )
        out = await svc._get_wallet_balances(allowed_addresses={OWNER_WALLET.lower()})
        ids = {w["wallet_id"] for w in out["wallets"]}
        assert ids == {"w1"}
        assert out["total_wallets"] == 1

    @pytest.mark.asyncio
    async def test_admin_none_returns_all(self) -> None:
        from coordinator_api.contexts.portfolio.services.portfolio_aggregation_service import (
            PortfolioAggregationService,
        )

        svc = PortfolioAggregationService()
        svc.http_client = _FakeClient(
            [
                {"wallet_id": "w1", "address": OWNER_WALLET, "public_key": "pk1"},
                {"wallet_id": "w2", "address": FOREIGN_WALLET, "public_key": "pk2"},
            ]
        )
        out = await svc._get_wallet_balances(allowed_addresses=None)
        assert {w["wallet_id"] for w in out["wallets"]} == {"w1", "w2"}

    @pytest.mark.asyncio
    async def test_error_string_not_leaked(self) -> None:
        from coordinator_api.contexts.portfolio.services.portfolio_aggregation_service import (
            PortfolioAggregationService,
        )

        class _Boom:
            async def get(self, url, headers=None):
                raise RuntimeError("secret internal detail")

        svc = PortfolioAggregationService()
        svc.http_client = _Boom()
        out = await svc._get_wallet_balances()
        assert "secret internal detail" not in str(out.get("error", ""))
