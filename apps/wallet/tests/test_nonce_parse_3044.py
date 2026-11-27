"""#3044 (AUDIT-WALLET-NONCE-FABRICATE-1) — malformed account-RPC nonce must
never fabricate 0.

``int(account_data.get("nonce", 0))`` answered nonce 0 for every malformed
shape — missing, null, string, bool, negative, float, non-dict — and a
fabricated 0 signs a doomed envelope (nonce conflict at the node). On the
shared-payout-account lanes that also burns the serialized payout slot.

Contract (same as #3015/#3041): only a real non-negative int counts —
explicit ``0`` stays valid; everything else is "no nonce source" and each
site fails closed through its existing path:

- ``bridge_monitor._mint_deposit``  → re-pend the row, never submit
- ``bridge_routes`` withdraw/build  → 503, no unsigned tx returned
- ``bridge_withdraw_monitor._refund_nonce`` → raise, refund row fails
- ``sell_escrow_monitor._account_view`` → raise, per-row containment skips
- ``keystore._get_account_nonce``   → ValueError propagates, nothing signed

``api_rest.py``'s ``result.get("nonce", 0)`` echoes the wallet's own
submit result, not an RPC account read — verified benign, unchanged.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from aitbc.utils import units_to_ait

from wallet_app.rpc_parse import parse_account_balance, parse_account_nonce, parse_uint_field

MALFORMED_NONCES: list[Any] = [
    {},
    {"nonce": None},
    {"nonce": "5"},
    {"nonce": True},
    {"nonce": False},
    {"nonce": -1},
    {"nonce": 1.5},
    {"nonce": 0.0},
    [],
    "not-a-dict",
    None,
]


class TestParseHelpers:
    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    def test_malformed_nonce_returns_none(self, payload):
        assert parse_account_nonce(payload) is None

    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    def test_malformed_balance_returns_none(self, payload):
        assert parse_account_balance(payload) is None

    @pytest.mark.parametrize("payload", [{"nonce": 0}, {"nonce": 7}, {"nonce": 2**40}])
    def test_real_non_negative_int_nonce_accepted(self, payload):
        assert parse_account_nonce(payload) == payload["nonce"]

    @pytest.mark.parametrize("payload", [{"balance": 0}, {"balance": 12345}])
    def test_real_non_negative_int_balance_accepted(self, payload):
        assert parse_account_balance(payload) == payload["balance"]

    def test_bool_is_not_an_int(self):
        assert parse_uint_field({"nonce": True}, "nonce") is None
        assert parse_uint_field({"nonce": False}, "nonce") is None


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "http://chain.test/x"),
                response=httpx.Response(self.status_code, json=self._data),
            )

    def json(self):
        return self._data


def _route(routes: dict[str, Any], url: str, method: str, default: Any = None) -> _Resp:
    """First ``routes`` entry ``(method, payload[, status])`` whose key is a
    substring of ``url``; scripted Exceptions raise, ``default`` answers
    unmatched POSTs."""
    for match, spec in routes.items():
        if spec[0] != method or match not in url:
            continue
        payload = spec[1]
        if isinstance(payload, Exception):
            raise payload
        status = spec[2] if len(spec) > 2 else 200
        return _Resp(payload, status_code=status)
    if default is None:
        raise AssertionError(f"unexpected {method} {url}")
    return _Resp(default)


def _async_client_class(routes: dict[str, Any], posts: list[dict[str, Any]] | None = None):
    """Build an httpx.AsyncClient stand-in routing GET/POST by URL substring;
    every POST body is recorded in ``posts`` when given."""

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _route(routes, url, "GET")

        async def post(self, url, json=None, **kwargs):
            if posts is not None:
                posts.append(json or {})
            return _route(routes, url, "POST", default={"transaction_hash": "0x" + "ab" * 32})

    return _Client


# ---------------------------------------------------------------------------
# bridge_monitor._mint_deposit — highest risk: signs TRANSFER from
# GENESIS_WALLET_ADDRESS (shared payout account with bridge-monitor).
# ---------------------------------------------------------------------------


def _arm_mint(monkeypatch, tmp_path: Path, account_payload: Any):
    from wallet_app.bridge import bridge_db
    from wallet_app.bridge import bridge_monitor as bm

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(bridge_db, "DB_PATH", str(db_path))
    bridge_db.init_db()

    recipient = "0x" + "d" * 40
    deposit_id = bridge_db.insert_deposit("0xeth1", "0xfrom", Decimal("1"), Decimal("100"), recipient=recipient)

    posts: list[dict[str, Any]] = []

    class _NonceGet:
        @staticmethod
        async def get(url, **kwargs):
            return _Resp(account_payload)

    monkeypatch.setattr(bm, "SharedHttpClient", _NonceGet)
    monkeypatch.setattr(bm, "GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setattr(bm, "BLOCKCHAIN_RPC_URL", "http://test-rpc")
    monkeypatch.setenv("CHAIN_ID", "test-chain")
    monkeypatch.setattr(bm.httpx, "AsyncClient", _async_client_class({}, posts))
    return bm, bridge_db, deposit_id, recipient, posts


class TestMintDepositNonce:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    async def test_malformed_nonce_repends_and_never_submits(self, tmp_path, monkeypatch, payload):
        bm, bridge_db, deposit_id, recipient, posts = _arm_mint(monkeypatch, tmp_path, payload)

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        row = bridge_db.get_deposit_by_id(deposit_id)
        assert row["status"] == "pending"
        assert posts == []

    @pytest.mark.asyncio
    async def test_explicit_zero_nonce_proceeds(self, tmp_path, monkeypatch):
        bm, bridge_db, deposit_id, recipient, posts = _arm_mint(monkeypatch, tmp_path, {"nonce": 0})

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        assert len(posts) == 1
        assert posts[0]["nonce"] == 0
        assert bridge_db.get_deposit_by_id(deposit_id)["status"] == "completed"

    @pytest.mark.asyncio
    async def test_valid_nonce_proceeds(self, tmp_path, monkeypatch):
        bm, bridge_db, deposit_id, recipient, posts = _arm_mint(monkeypatch, tmp_path, {"nonce": 7})

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        assert len(posts) == 1
        assert posts[0]["nonce"] == 7
        assert bridge_db.get_deposit_by_id(deposit_id)["status"] == "completed"


# ---------------------------------------------------------------------------
# bridge_routes /withdraw/build — unsigned BRIDGE_WITHDRAW prep.
# ---------------------------------------------------------------------------


async def _call_withdraw_build(monkeypatch, account_payload):
    from fastapi import HTTPException

    from wallet_app.bridge import bridge_routes as br

    class _GetClient:
        @staticmethod
        async def get(url, **kwargs):
            return _Resp(account_payload)

    monkeypatch.setattr(br, "SharedHttpClient", _GetClient)
    monkeypatch.setattr(br, "resolve_chain_id", lambda: "test-chain")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://test-rpc")

    async def fake_estimate(ait_amount):
        return {
            "fee_ait": Decimal("0.01"),
            "net_ait": Decimal("0.99"),
            "amount_eth": Decimal("0.00040000"),
        }

    monkeypatch.setattr(br, "calculate_eth_amount", fake_estimate)

    from eth_utils import to_checksum_address

    body = {
        "ait_amount": "1",
        "eth_address": to_checksum_address("0x" + "e" * 40),
        "from_address": to_checksum_address("0x" + "f" * 40),
    }
    try:
        result = await br.bridge_withdraw_build(body)
    except HTTPException as exc:
        return exc.status_code, None
    return 200, result


class TestWithdrawBuildNonce:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    async def test_malformed_nonce_is_503_no_unsigned_tx(self, monkeypatch, payload):
        status, result = await _call_withdraw_build(monkeypatch, payload)
        assert status == 503
        assert result is None

    @pytest.mark.asyncio
    async def test_explicit_zero_nonce_proceeds(self, monkeypatch):
        status, result = await _call_withdraw_build(monkeypatch, {"nonce": 0})
        assert status == 200
        assert result["instructions"]["body"]["nonce"] == 0

    @pytest.mark.asyncio
    async def test_valid_nonce_proceeds(self, monkeypatch):
        status, result = await _call_withdraw_build(monkeypatch, {"nonce": 42})
        assert status == 200
        assert result["instructions"]["body"]["nonce"] == 42


# ---------------------------------------------------------------------------
# bridge_withdraw_monitor._refund_nonce — sealed nonce for refund TRANSFER.
# ---------------------------------------------------------------------------


@pytest.fixture
def withdraw_monitor_env(monkeypatch):
    """bridge_withdraw_monitor with a test RPC URL — _refund_nonce needs no DB."""
    from wallet_app.bridge import bridge_withdraw_monitor as monitor

    monkeypatch.setattr(monitor, "BLOCKCHAIN_RPC_URL", "http://test-rpc")
    monkeypatch.setattr(monitor, "GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    return monitor


class TestRefundNonce:
    def _arm(self, monitor_env, monkeypatch, account_payload):
        routes = {
            "/rpc/account/": ("GET", account_payload),
            "/mempool": ("GET", {"transactions": []}),
        }
        monkeypatch.setattr(monitor_env.httpx, "AsyncClient", _async_client_class(routes))
        return monitor_env

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    async def test_malformed_nonce_raises_no_sign(self, withdraw_monitor_env, monkeypatch, payload):
        self._arm(withdraw_monitor_env, monkeypatch, payload)
        with pytest.raises(Exception, match="malformed account nonce"):
            await withdraw_monitor_env._refund_nonce()

    @pytest.mark.asyncio
    async def test_explicit_zero_nonce_proceeds(self, withdraw_monitor_env, monkeypatch):
        self._arm(withdraw_monitor_env, monkeypatch, {"nonce": 0})
        assert await withdraw_monitor_env._refund_nonce() == 0

    @pytest.mark.asyncio
    async def test_valid_nonce_proceeds(self, withdraw_monitor_env, monkeypatch):
        self._arm(withdraw_monitor_env, monkeypatch, {"nonce": 9})
        assert await withdraw_monitor_env._refund_nonce() == 9


# ---------------------------------------------------------------------------
# sell_escrow_monitor._account_view — (nonce, balance) for escrow ops.
# ---------------------------------------------------------------------------


class TestAccountView:
    def _arm(self, monkeypatch, payload, status_code: int = 200):
        from wallet_app.bridge import sell_escrow_monitor as sellmon

        routes = {"/rpc/account/": ("GET", payload, status_code)}
        monkeypatch.setattr(sellmon.httpx, "AsyncClient", _async_client_class(routes))
        monkeypatch.setattr(sellmon.wdm, "BLOCKCHAIN_RPC_URL", "http://test-rpc")
        return sellmon

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    async def test_malformed_nonce_raises(self, monkeypatch, payload):
        # Keep balance valid so only the nonce field is malformed; non-dict
        # payloads fail both fields.
        if isinstance(payload, dict):
            payload = {**payload, "balance": 100}
        sellmon = self._arm(monkeypatch, payload)
        with pytest.raises(ValueError, match="malformed account response"):
            await sellmon._account_view("0x" + "1" * 40)

    @pytest.mark.asyncio
    async def test_malformed_balance_raises(self, monkeypatch):
        sellmon = self._arm(monkeypatch, {"nonce": 3, "balance": "lots"})
        with pytest.raises(ValueError, match="malformed account response"):
            await sellmon._account_view("0x" + "1" * 40)

    @pytest.mark.asyncio
    async def test_explicit_zero_nonce_proceeds(self, monkeypatch):
        sellmon = self._arm(monkeypatch, {"nonce": 0, "balance": 500})
        nonce, balance = await sellmon._account_view("0x" + "1" * 40)
        assert nonce == 0
        assert balance == units_to_ait(500)

    @pytest.mark.asyncio
    async def test_valid_nonce_proceeds(self, monkeypatch):
        sellmon = self._arm(monkeypatch, {"nonce": 12, "balance": 1000})
        nonce, balance = await sellmon._account_view("0x" + "1" * 40)
        assert nonce == 12
        assert balance == units_to_ait(1000)

    @pytest.mark.asyncio
    async def test_404_still_reads_as_zero(self, monkeypatch):
        sellmon = self._arm(monkeypatch, {}, status_code=404)
        nonce, balance = await sellmon._account_view("0x" + "1" * 40)
        assert (nonce, balance) == (0, Decimal("0"))


# ---------------------------------------------------------------------------
# keystore._get_account_nonce — feeds sign_and_submit_transaction.
# ---------------------------------------------------------------------------


class TestKeystoreAccountNonce:
    def _arm(self, monkeypatch, payload):
        import wallet_app.keystore.persistent_service as svc

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(svc.httpx, "get", lambda *a, **k: Resp())
        monkeypatch.setattr(svc, "settings", type("S", (), {"blockchain_rpc_url": "http://test-rpc"})())
        return svc

    @pytest.mark.parametrize("payload", MALFORMED_NONCES)
    def test_malformed_nonce_raises_valueerror(self, keystore, monkeypatch, payload):
        self._arm(monkeypatch, payload)
        with pytest.raises(ValueError, match="malformed account nonce"):
            keystore._get_account_nonce("0x" + "1" * 40)

    def test_explicit_zero_nonce_returns_zero(self, keystore, monkeypatch):
        self._arm(monkeypatch, {"nonce": 0})
        assert keystore._get_account_nonce("0x" + "1" * 40) == 0

    def test_valid_nonce_returns_value(self, keystore, monkeypatch):
        self._arm(monkeypatch, {"nonce": 33})
        assert keystore._get_account_nonce("0x" + "1" * 40) == 33
