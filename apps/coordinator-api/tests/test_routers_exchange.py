"""Router tests for /v1/exchange/* (#1289 round 9 batch 4).

ETH->AITBC payment-request surface on RedisStateManager (in-memory
fallback in tests). monitor_payment is an infinite background loop
(expiry horizon = 1h) — patched to a no-op; it is a boundary concern,
not route logic. Honest-stub contract: confirm-payment is a documented
501 (free-minting guard).

Matrix note: /v1/exchange/* = CLIENT admits ONLY role 'client' — admin
is excluded by check_role_match(CLIENT,'admin')==False. Flagged as an
observation (policy choice vs defect) on the #1289 ledger.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import coordinator_api.contexts.infrastructure.routers.exchange as exch_mod
from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level

BASE = "/v1/exchange"
RATE = Decimal("1000")  # 1 ETH = 1000 AITBC


@pytest.fixture(autouse=True)
def _no_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(payment_id: str) -> None:
        return None

    monkeypatch.setattr(exch_mod, "monitor_payment", _noop)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


def _payment(aitbc: str = "1000", eth: str = "1", **over) -> dict:
    body = {"user_id": "user-1", "aitbc_amount": aitbc, "eth_amount": eth}
    body.update(over)
    return body


class TestExchangeMatrix:
    def test_rates_and_stats_public(self) -> None:
        assert get_auth_level("/v1/exchange/rates") == AuthLevel.NONE
        assert get_auth_level("/v1/exchange/market-stats") == AuthLevel.NONE

    def test_create_payment_client_only(self) -> None:
        # CLIENT level admits 'client' and rejects 'admin'/'miner' per
        # check_role_match — admin exclusion noted on #1289 ledger
        level = get_auth_level("/v1/exchange/create-payment")
        assert level == AuthLevel.CLIENT
        assert check_role_match(level, "client")
        assert not check_role_match(level, "admin")
        assert not check_role_match(level, "miner")


class TestPaymentLifecycle:
    def test_create_and_status(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/create-payment", json=_payment(), headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["payment_id"]
        assert body["status"] == "pending"
        assert body["user_id"] == "user-1"
        assert Decimal(str(body["aitbc_amount"])) == Decimal("1000")

        status = client.get(f"{BASE}/payment-status/{body['payment_id']}", headers=_headers())
        assert status.status_code == 200
        assert status.json()["status"] == "pending"

    def test_amount_mismatch_400(self, client: TestClient) -> None:
        # 1000 AITBC requires exactly 1 ETH at the peg
        resp = client.post(f"{BASE}/create-payment", json=_payment(eth="2"), headers=_headers())
        assert resp.status_code == 400

    def test_nonpositive_amounts_rejected(self, client: TestClient) -> None:
        # pydantic gt=0 rejects at validation (422) before the handler's 400 check
        assert client.post(f"{BASE}/create-payment", json=_payment(aitbc="0"), headers=_headers()).status_code == 422

    def test_status_unknown_404(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/payment-status/ghost", headers=_headers()).status_code == 404

    def test_confirm_payment_disabled_501(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/confirm-payment/abc", params={"tx_hash": "0xdead"}, headers=_headers())
        assert resp.status_code == 501


class TestRatesAndStats:
    def test_rates(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/rates")
        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(str(body["eth_to_aitbc"])) == RATE
        assert Decimal(str(body["aitbc_to_eth"])) == Decimal("0.001")

    def test_market_stats_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/market-stats")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("price", "price_change_24h", "daily_volume", "total_payments", "pending_payments"):
            assert key in body

    def test_agents_test_endpoint(self, client: TestClient) -> None:
        # route lives at /v1/agents/test (exchange router has no path prefix)
        resp = client.get("/v1/agents/test", headers=_headers())
        assert resp.status_code == 200
