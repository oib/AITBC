"""Coverage for the exchange-compat and settlement routers.

The exchange endpoints were migrated from coordinator-api; the settlement
endpoints drive the v0.9.0 HTLC flow.  External infra is fully mocked:
``SettlementClient`` is replaced by a fake, ``_monitor_payment`` is stubbed
(it would otherwise sleep-loop for the payment timeout inside TestClient),
and the webhook HMAC secret is injected via ``monkeypatch``.
"""

import hashlib
import hmac
import time
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from trading_service.storage import engine


EXCHANGE_RATE = 100000  # mirrors ETHEREUM_CONFIG["exchange_rate"]


def _sig(payment_id: str, tx_hash: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"{payment_id}:{tx_hash}".encode(), hashlib.sha256).hexdigest()


async def _seed_exchange_payment(**overrides):
    from trading_service.domain.exchange_payment import ExchangePayment

    suffix = uuid4().hex[:8]
    now = int(time.time())
    kwargs = {
        "payment_id": f"ex_test_{suffix}",
        "user_id": "user-a",
        "aitbc_amount": Decimal("100"),
        "eth_amount": Decimal("0.001"),
        "payment_address": "0x0000000000000000000000000000000000000000",
        "status": "pending",
        "created_at": now,
        "expires_at": now + 3600,
        "confirmations": 0,
    }
    kwargs.update(overrides)
    async with AsyncSession(engine) as session:
        session.add(ExchangePayment(**kwargs))
        await session.commit()
    return kwargs["payment_id"]


async def _seed_inter_chain_trade(**overrides):
    from trading_service.domain.inter_chain import InterChainTrade

    kwargs = {
        "source_chain": "chain-a",
        "dest_chain": "chain-b",
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "amount": 100,
        "price": Decimal("1.0"),
        "status": "pending",
    }
    kwargs.update(overrides)
    async with AsyncSession(engine) as session:
        trade = InterChainTrade(**kwargs)
        session.add(trade)
        await session.commit()
        await session.refresh(trade)
        return trade.trade_id


async def _trade_row(trade_id: str):
    """Fetch the persisted trade row for assertions."""
    from sqlalchemy import select

    from trading_service.domain.inter_chain import InterChainTrade

    async with AsyncSession(engine) as session:
        result = await session.execute(select(InterChainTrade).where(InterChainTrade.trade_id == trade_id))
        return result.scalars().first()


# ---------------------------------------------------------------------------
# Exchange compat — payment creation, status, rates, stats
# ---------------------------------------------------------------------------


class TestExchangePaymentCreation:
    @pytest.fixture(autouse=True)
    def _no_monitor(self, monkeypatch):
        """Stub the background payment monitor — it sleeps 30s per loop."""

        async def _noop(_payment_id: str) -> None:
            return None

        monkeypatch.setattr("trading_service.routers.exchange_compat._monitor_payment", _noop)

    def test_create_payment_happy_path(self, client):
        resp = client.post(
            "/v1/exchange/create-payment",
            json={"user_id": "user-x", "aitbc_amount": "100", "eth_amount": str(Decimal(100) / EXCHANGE_RATE)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "user-x"
        assert body["status"] == "pending"
        assert body["payment_id"].startswith("ex_")
        assert Decimal(body["aitbc_amount"]) == Decimal("100")
        assert Decimal(body["eth_amount"]) == Decimal(100) / EXCHANGE_RATE

    def test_create_payment_rejects_nonpositive_amounts(self, client):
        for body in (
            {"user_id": "u", "aitbc_amount": "0", "eth_amount": "0"},
            {"user_id": "u", "aitbc_amount": "-5", "eth_amount": "-0.00005"},
            {"user_id": "u", "aitbc_amount": "100", "eth_amount": "0"},
        ):
            resp = client.post("/v1/exchange/create-payment", json=body)
            assert resp.status_code in (400, 422), body

    def test_create_payment_rejects_amount_mismatch(self, client):
        resp = client.post(
            "/v1/exchange/create-payment",
            json={"user_id": "u", "aitbc_amount": "100", "eth_amount": "999"},
        )
        assert resp.status_code == 400

    def test_create_payment_requires_api_key(self):
        from fastapi.testclient import TestClient
        from trading_service.main import app

        anon = TestClient(app)
        resp = anon.post(
            "/v1/exchange/create-payment",
            json={"user_id": "u", "aitbc_amount": "100", "eth_amount": "0.001"},
        )
        assert resp.status_code in (401, 403)

    async def test_idempotent_replay_returns_same_payment(self, client):
        key = f"idem-{uuid4().hex}"
        payload = {"user_id": "user-idem", "aitbc_amount": "50", "eth_amount": str(Decimal(50) / EXCHANGE_RATE)}
        headers = {"Idempotency-Key": key}
        r1 = client.post("/v1/exchange/create-payment", json=payload, headers=headers)
        r2 = client.post("/v1/exchange/create-payment", json=payload, headers=headers)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["payment_id"] == r2.json()["payment_id"]

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-IDEM-1 (#1417): the Idempotency-Key lookup is not scoped to "
        "user_id — a second user replaying the same key receives the first "
        "user's payment record (amounts, address, payment_id)",
    )
    async def test_idempotency_key_is_scoped_to_user(self, client):
        key = f"idem-{uuid4().hex}"
        r1 = client.post(
            "/v1/exchange/create-payment",
            json={"user_id": "user-a", "aitbc_amount": "50", "eth_amount": str(Decimal(50) / EXCHANGE_RATE)},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200
        # Different user, same key: must NOT see user-a's payment
        r2 = client.post(
            "/v1/exchange/create-payment",
            json={"user_id": "user-b", "aitbc_amount": "50", "eth_amount": str(Decimal(50) / EXCHANGE_RATE)},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code in (403, 404, 409)
        assert r2.json().get("payment_id") != r1.json()["payment_id"]


class TestExchangePaymentStatus:
    async def test_status_pending(self, client):
        pid = await _seed_exchange_payment(status="pending")
        resp = client.get(f"/v1/exchange/payment-status/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_status_missing_404(self, client):
        resp = client.get("/v1/exchange/payment-status/ex_nonexistent")
        assert resp.status_code == 404

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-DB-1 (#1411): the expire path commits then reads "
        "expired attributes off the AsyncSession → greenlet_spawn 500",
    )
    async def test_pending_payment_expires_lazily(self, client):
        pid = await _seed_exchange_payment(status="pending", expires_at=int(time.time()) - 10)
        resp = client.get(f"/v1/exchange/payment-status/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "expired"
        # Second read stays expired (persisted)
        resp2 = client.get(f"/v1/exchange/payment-status/{pid}")
        assert resp2.json()["status"] == "expired"

    async def test_confirmed_payment_does_not_expire(self, client):
        pid = await _seed_exchange_payment(status="confirmed", expires_at=int(time.time()) - 10)
        resp = client.get(f"/v1/exchange/payment-status/{pid}")
        assert resp.json()["status"] == "confirmed"


class TestExchangeWebhookConfirm:
    @pytest.fixture(autouse=True)
    def _secret(self, monkeypatch):
        monkeypatch.setenv("EXCHANGE_WEBHOOK_SECRET", "test-webhook-secret")

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-DB-1 (#1411): confirm commits status='confirmed' then "
        "reads payment.aitbc_amount off the expired session → 500 to the "
        "webhook caller even though the DB row was flipped",
    )
    async def test_confirm_payment_valid_signature(self, client):
        pid = await _seed_exchange_payment(status="pending")
        tx = "0xdeadbeef"
        resp = client.post(
            f"/v1/exchange/confirm-payment/{pid}",
            params={"tx_hash": tx},
            headers={"X-Signature": _sig(pid, tx, "test-webhook-secret")},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        status = client.get(f"/v1/exchange/payment-status/{pid}")
        assert status.json()["status"] == "confirmed"
        assert status.json()["tx_hash"] == tx

    async def test_confirm_payment_bad_signature_401(self, client):
        pid = await _seed_exchange_payment(status="pending")
        resp = client.post(
            f"/v1/exchange/confirm-payment/{pid}",
            params={"tx_hash": "0xabc"},
            headers={"X-Signature": "bogus"},
        )
        assert resp.status_code == 401

    async def test_confirm_payment_no_secret_configured_401(self, client, monkeypatch):
        monkeypatch.delenv("EXCHANGE_WEBHOOK_SECRET", raising=False)
        pid = await _seed_exchange_payment(status="pending")
        resp = client.post(
            f"/v1/exchange/confirm-payment/{pid}",
            params={"tx_hash": "0xabc"},
            headers={"X-Signature": "anything"},
        )
        assert resp.status_code == 401

    async def test_confirm_payment_non_pending_rejected(self, client):
        pid = await _seed_exchange_payment(status="confirmed")
        tx = "0xabc"
        resp = client.post(
            f"/v1/exchange/confirm-payment/{pid}",
            params={"tx_hash": tx},
            headers={"X-Signature": _sig(pid, tx, "test-webhook-secret")},
        )
        assert resp.status_code == 400

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-MONEY-1 (#1410): confirm-payment accepts ANY tx_hash with only an "
        "HMAC check — no on-chain verification — and 'minting' is a log line, "
        "not a mint. The coordinator-api deliberately disabled this exact "
        "endpoint (HTTP 501) for free-minting; the trading migration "
        "re-enabled it",
    )
    async def test_confirm_payment_rejects_unverified_txhash(self, client):
        """Until real tx verification + minting exist, confirmation must be
        refused like coordinator-api's 501 — a syntactically valid but
        completely fabricated tx_hash must not flip a payment to confirmed."""
        pid = await _seed_exchange_payment(status="pending")
        tx = "0x" + "00" * 32  # well-formed but never broadcast
        resp = client.post(
            f"/v1/exchange/confirm-payment/{pid}",
            params={"tx_hash": tx},
            headers={"X-Signature": _sig(pid, tx, "test-webhook-secret")},
        )
        assert resp.status_code in (400, 422, 501, 502)


class TestExchangeReadEndpoints:
    def test_rates(self, client):
        resp = client.get("/v1/exchange/rates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["eth_to_aitbc"] == EXCHANGE_RATE

    def test_wallet_endpoints_are_honest_stubs(self, client):
        for path in ("/v1/exchange/wallet/balance", "/v1/exchange/wallet/info"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.json()["balance"] == 0.0

    async def test_market_stats_counts_confirmed(self, client):
        # The stats are global across the shared test DB — measure the delta.
        before = client.get("/v1/exchange/market-stats").json()

        now = int(time.time())
        await _seed_exchange_payment(status="confirmed", confirmed_at=now, aitbc_amount=Decimal("200"))
        await _seed_exchange_payment(status="confirmed", confirmed_at=now - 48 * 3600, aitbc_amount=Decimal("999"))
        await _seed_exchange_payment(status="pending")

        resp = client.get("/v1/exchange/market-stats")
        assert resp.status_code == 200
        body = resp.json()
        # Only the fresh confirmed payment counts toward 24h volume
        assert Decimal(body["daily_volume"]) == Decimal(before["daily_volume"]) + Decimal("200")
        assert body["total_payments"] == before["total_payments"] + 2
        assert body["pending_payments"] == before["pending_payments"] + 1


# ---------------------------------------------------------------------------
# Settlement router — escrow lock / settle / status
# ---------------------------------------------------------------------------


class _FakeSettlementClient:
    """Stand-in for aitbc.settlement.client.SettlementClient."""

    def __init__(self, escrow=None, settle_result=None, escrow_status="escrow_locked", fail=False):
        self._escrow = escrow or {
            "escrow_id": "esc-123",
            "status": "created",
            "secret_hash": "0xhash",
            "source_timelock": 100,
            "dest_timelock": 90,
        }
        self._settle_result = settle_result or {"status": "settled", "escrow_id": "esc-123"}
        self._escrow_status = escrow_status
        self._fail = fail
        self.created_with = None
        self.settled_with = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def create_escrow(self, **kwargs):
        self.created_with = kwargs
        if self._fail:
            raise RuntimeError("node down")
        return self._escrow

    async def settle(self, escrow_id, secret):
        self.settled_with = (escrow_id, secret)
        if self._fail:
            raise RuntimeError("settle failed")
        return self._settle_result

    async def get_escrow_status(self, escrow_id):
        if self._fail:
            raise RuntimeError("status failed")
        return self._escrow_status


def _patch_settlement_client(monkeypatch, fake: _FakeSettlementClient):
    monkeypatch.setattr(
        "trading_service.routers.settlement._get_settlement_client",
        lambda: fake,
    )


class TestSettlementLockEscrow:
    async def test_lock_escrow_404(self, client):
        resp = client.post("/v1/trading/trades/trade_missing/lock-escrow", json={})
        assert resp.status_code == 404

    async def test_lock_escrow_rejects_nonpositive_amount(self, client):
        trade_id = await _seed_inter_chain_trade(amount=0)
        resp = client.post(f"/v1/trading/trades/{trade_id}/lock-escrow", json={})
        assert resp.status_code == 400

    async def test_lock_escrow_happy_path(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(amount=250)
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/lock-escrow", json={"timeout_seconds": 60})
        assert resp.status_code == 200
        body = resp.json()
        assert body["escrow_id"] == "esc-123"
        assert body["secret_hash"] == "0xhash"

        # RPC received the trade's chain/party fields
        assert fake.created_with["trade_id"] == trade_id
        assert fake.created_with["source_chain"] == "chain-a"
        assert fake.created_with["dest_chain"] == "chain-b"
        assert fake.created_with["amount"] == 250
        assert fake.created_with["timeout_seconds"] == 60

        row = await _trade_row(trade_id)
        assert row.escrow_id == "esc-123"
        assert row.secret_hash == "0xhash"
        assert row.source_timelock == 100
        assert row.dest_timelock == 90

    async def test_lock_escrow_idempotent_409(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-existing", settlement_phase="pending")
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/lock-escrow", json={})
        assert resp.status_code == 409
        assert resp.json()["escrow_id"] == "esc-existing"
        # No second escrow was created
        assert fake.created_with is None

    async def test_lock_escrow_rpc_failure_502_and_no_state(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(amount=100)
        _patch_settlement_client(monkeypatch, _FakeSettlementClient(fail=True))

        resp = client.post(f"/v1/trading/trades/{trade_id}/lock-escrow", json={})
        assert resp.status_code == 502
        row = await _trade_row(trade_id)
        assert row.escrow_id is None
        assert row.settlement_phase == "none"

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-GUARD-1 (#1415): lock_escrow does not check trade.status — an "
        "escrow can be created for a cancelled/completed trade, stranding "
        "funds in an HTLC nobody will settle",
    )
    async def test_lock_escrow_rejects_terminal_trade(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(amount=100, status="cancelled")
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/lock-escrow", json={})
        assert resp.status_code in (400, 409)
        assert fake.created_with is None

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-ENUM-1 (#1414): lock_escrow writes settlement_phase='pending' "
        "which is not a SettlementPhase value (none/escrow_created/…/settled) "
        "— the column comment says it stores SettlementPhase values",
    )
    async def test_lock_escrow_writes_enum_phase(self, client, monkeypatch):
        from aitbc.trading.types import SettlementPhase

        trade_id = await _seed_inter_chain_trade(amount=100)
        _patch_settlement_client(monkeypatch, _FakeSettlementClient())

        resp = client.post(f"/v1/trading/trades/{trade_id}/lock-escrow", json={})
        assert resp.status_code == 200
        row = await _trade_row(trade_id)
        assert row.settlement_phase in {p.value for p in SettlementPhase}


class TestSettlementSettle:
    async def test_settle_404(self, client):
        resp = client.post("/v1/trading/trades/trade_missing/settle", json={"secret": "s"})
        assert resp.status_code == 404

    async def test_settle_requires_escrow(self, client):
        trade_id = await _seed_inter_chain_trade()
        resp = client.post(f"/v1/trading/trades/{trade_id}/settle", json={"secret": "s3cr3t"})
        assert resp.status_code == 400
        assert "escrow" in resp.json()["error"].lower()

    async def test_settle_happy_path(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="pending")
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/settle", json={"secret": "s3cr3t"})
        assert resp.status_code == 200
        assert resp.json()["result"]["status"] == "settled"
        assert fake.settled_with == ("esc-123", "s3cr3t")

        row = await _trade_row(trade_id)
        assert row.settlement_phase == "completed"

    async def test_settle_already_completed_idempotent(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="completed")
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/settle", json={"secret": "s3cr3t"})
        assert resp.status_code == 200
        assert resp.json()["result"] == "already_settled"
        # RPC not called again
        assert fake.settled_with is None

    async def test_settle_rpc_failure_502(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="pending")
        _patch_settlement_client(monkeypatch, _FakeSettlementClient(fail=True))

        resp = client.post(f"/v1/trading/trades/{trade_id}/settle", json={"secret": "s3cr3t"})
        assert resp.status_code == 502
        row = await _trade_row(trade_id)
        assert row.settlement_phase == "pending"

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-ENUM-1 (#1414): the already-settled guard checks "
        "settlement_phase == 'completed', but SettlementPhase's terminal "
        "value is 'settled' — a trade settled by any other writer "
        "(settlement monitor, v0.9.0 flow) would be settled a second time",
    )
    async def test_settle_recognizes_settled_phase(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="settled")
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/settle", json={"secret": "s3cr3t"})
        assert resp.status_code == 200
        assert resp.json()["result"] == "already_settled"
        assert fake.settled_with is None

    @pytest.mark.xfail(
        strict=True,
        reason="TRADING-GUARD-1 (#1415): settle accepts any trade carrying an "
        "escrow_id regardless of settlement_phase — e.g. phase 'refunded' "
        "or trade status 'cancelled' can still be settled",
    )
    async def test_settle_rejects_refunded_phase(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="refunded", status="cancelled")
        fake = _FakeSettlementClient()
        _patch_settlement_client(monkeypatch, fake)

        resp = client.post(f"/v1/trading/trades/{trade_id}/settle", json={"secret": "s3cr3t"})
        assert resp.status_code in (400, 409)
        assert fake.settled_with is None


class TestSettlementStatus:
    async def test_status_without_escrow(self, client):
        trade_id = await _seed_inter_chain_trade()
        resp = client.get(f"/v1/trading/trades/{trade_id}/settlement-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["settlement_phase"] == "none"
        assert body["escrow_id"] is None
        assert "escrow_status" not in body

    async def test_status_with_escrow_queries_rpc(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="pending")
        _patch_settlement_client(monkeypatch, _FakeSettlementClient(escrow_status="escrow_locked"))

        resp = client.get(f"/v1/trading/trades/{trade_id}/settlement-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["escrow_id"] == "esc-123"
        assert body["escrow_status"] == "escrow_locked"

    async def test_status_rpc_failure_degrades(self, client, monkeypatch):
        trade_id = await _seed_inter_chain_trade(escrow_id="esc-123", settlement_phase="pending")
        _patch_settlement_client(monkeypatch, _FakeSettlementClient(fail=True))

        resp = client.get(f"/v1/trading/trades/{trade_id}/settlement-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["escrow_status"] == "unknown"
        assert "error" in body

    async def test_status_404(self, client):
        resp = client.get("/v1/trading/trades/trade_missing/settlement-status")
        assert resp.status_code == 404
