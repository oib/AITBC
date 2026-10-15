"""ETH-8 phase 3 (C5) — the wallet-side exchange settlement monitor.

Throwaway DBs only (bridge_deposits.db + a real exchange.db under
tmp_path); chain/ETH RPC calls are stubbed at the module seams and the
loopback endpoint is stubbed at ``_post_event`` — no network, no live
ledger, no keys.
"""

import json
import logging
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from wallet_app.bridge import bridge_db
from wallet_app.bridge import bridge_withdraw_monitor as wdm
from wallet_app.bridge import exchange_settlement_monitor as esm
from wallet_app.bridge import sell_escrow_monitor as sellmon
from wallet_app.bridge.bridge_db import (
    get_exchange_settlement,
    init_db,
    insert_exchange_prepay_deposit,
    insert_exchange_settlement,
    monitor_mark,
    update_exchange_settlement,
)

# Throwaway test keys — generated constants, never real material.
TEST_ETH_PRIVATE_KEY = "0x" + "11" * 32
TEST_ETH_ADDRESS = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"
TEST_ESCROW_KEY = "0x" + "22" * 32
TEST_TREASURY = "0x3333333333333333333333333333333333333333"
BUYER_AIT = "0x4444444444444444444444444444444444444444"
SELLER_AIT = "0x5555555555555555555555555555555555555555"
SELLER_ETH = "0xCf1719140054AB3fD52ce8aa3128dec9317426E3"


def _escrow_address() -> str:
    from eth_keys import keys as eth_keys

    return eth_keys.PrivateKey(bytes.fromhex("22" * 32)).public_key.to_checksum_address()


def _eth_rpc_stub(receipts: dict[str, Any] | None = None, nonces: dict[str, int] | None = None, block: int = 500):
    receipts = receipts if receipts is not None else {}
    nonces = nonces if nonces is not None else {"latest": 0, "pending": 0}

    async def _stub(method: str, params: list[Any]) -> Any:
        if method == "eth_getTransactionReceipt":
            return receipts.get(params[0])
        if method == "eth_getTransactionByHash":
            return None
        if method == "eth_blockNumber":
            return hex(block)
        if method == "eth_getTransactionCount":
            return hex(nonces.get(params[1], 0))
        if method == "eth_estimateGas":
            return hex(21_000)
        raise AssertionError(f"unexpected eth_rpc call {method}")

    return _stub


@pytest.fixture
def exchange_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Settlement-monitor environment: throwaway bridge + exchange DBs,
    escrow/signer configured, all chain/ETH seams stubbed, and _post_event
    captured so tests can drive the endpoint's answers."""
    bridge_db_path = tmp_path / "bridge.db"
    exchange_db_path = tmp_path / "exchange.db"
    escrow = _escrow_address()

    wallet_file = tmp_path / "escrow.json"
    wallet_file.write_text(json.dumps({"address": escrow, "private_key": TEST_ESCROW_KEY}))

    monkeypatch.setenv("BRIDGE_ENABLED", "true")
    monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
    monkeypatch.setenv("EXCHANGE_API_KEY", "test-internal-key")
    monkeypatch.setenv("EXCHANGE_INTERNAL_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{exchange_db_path}")
    monkeypatch.setenv("AIT_SELL_ESCROW", escrow)
    monkeypatch.setenv("SELL_ESCROW_WALLET_PATH", str(wallet_file))
    monkeypatch.delenv("SELL_ESCROW_CREDENTIAL_FILE", raising=False)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setenv("SELL_TREASURY_ADDRESS", TEST_TREASURY)
    monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
    monkeypatch.setenv("CHAIN_ID", "ait-testnet")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:0")
    monkeypatch.delenv("EXCHANGE_SETTLEMENT_MAX_ETH_PER_TX", raising=False)
    monkeypatch.delenv("ETH_WITHDRAW_MIN_RESERVE", raising=False)
    monkeypatch.delenv("BRIDGE_MAX_PAYOUT_FRACTION", raising=False)

    monkeypatch.setattr(wdm, "BRIDGE_ENABLED", True)
    monkeypatch.setattr(wdm, "ETH_WALLET_ADDRESS", TEST_ETH_ADDRESS)
    monkeypatch.setattr(wdm, "ETH_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
    monkeypatch.setattr(wdm, "BRIDGE_ADMIN_PRIVATE_KEY", "")
    monkeypatch.setattr(wdm, "ETH_WITHDRAW_GAS", "")
    monkeypatch.setattr(wdm, "BLOCKCHAIN_RPC_URL", "http://localhost:0")

    async def _coro(value):
        return value

    state: dict[str, Any] = {
        "posts": [],
        "post_responses": {},  # event -> (status, body) override
        "eth_sends": [],
        "ait_sends": [],
        "transfers": [],
        "escrow_nonce": 0,
        "escrow_balance": Decimal("1000"),
        "chain_height": 1000,
        "receipts": {},
        "nonces": {"latest": 0, "pending": 0},
        "eth_balance": Decimal("0.1"),
    }

    monkeypatch.setattr(wdm, "_eth_balance", lambda address: _coro(state["eth_balance"]))
    monkeypatch.setattr(wdm, "_eth_gas_price", lambda: _coro(1_000_000_000))
    monkeypatch.setattr(wdm, "_eth_nonce", lambda address: _coro(7))
    monkeypatch.setattr(wdm, "_eth_rpc", _eth_rpc_stub(receipts=state["receipts"], nonces=state["nonces"]))

    async def _broadcast(raw: str) -> str:
        state["eth_sends"].append(raw)
        return "0x" + "ee" * 32

    async def _ait_broadcast(tx: dict) -> str:
        state["ait_sends"].append(tx)
        return "0x" + "ff" * 32

    async def _account_view(address: str) -> tuple[int, Decimal]:
        return int(state["escrow_nonce"]), Decimal(str(state["escrow_balance"]))

    async def _transfers(address: str, limit: int = 0) -> list[dict]:
        return list(state["transfers"])

    async def _height() -> int:
        return int(state["chain_height"])

    async def _post_event(cfg: esm.ExchangeCfg, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        state["posts"].append(dict(payload))
        override = state["post_responses"].get(payload.get("event"))
        if override is not None:
            return override
        return 200, {"ok": True}

    monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast)
    monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _ait_broadcast)
    monkeypatch.setattr(sellmon, "_account_view", _account_view)
    monkeypatch.setattr(sellmon, "_fetch_transfers", _transfers)
    monkeypatch.setattr(sellmon, "_chain_height", _height)
    monkeypatch.setattr(esm, "_post_event", _post_event)
    monkeypatch.setattr(esm, "_db_initialized", False)
    monkeypatch.setattr(esm, "_exchange_polling_enabled", True)

    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(bridge_db_path)):
        init_db()
        # Real exchange schema via the app's own init_db.
        from apps.exchange.simple_exchange import db as exchange_db_mod

        exchange_db_mod.init_db()
        state["escrow"] = escrow
        state["exchange_db"] = str(exchange_db_path)
        yield state


def _cfg(env) -> esm.ExchangeCfg:
    return esm._exchange_config()


def _exdb(env) -> sqlite3.Connection:
    conn = sqlite3.connect(env["exchange_db"])
    conn.row_factory = sqlite3.Row
    return conn


def _insert_order(env, **over) -> int:
    args = {
        "order_type": "SELL",
        "amount": "10",
        "price": "0.001",
        "total": "0.01",
        "remaining": "10",
        "status": "open",
        "user_address": SELLER_AIT,
        "amount_ticks": 1_000_000_000,
        "price_ticks": 10_000,
        "filled_ticks": 0,
        "remaining_ticks": 1_000_000_000,
        "funded_state": "unfunded",
        "expiry_height": None,
        "backing_tx_hash": None,
        "locked_ticks": None,
        "seller_eth_address": None,
    }
    args.update(over)
    conn = _exdb(env)
    cols = ", ".join(args)
    marks = ", ".join("?" for _ in args)
    cur = conn.execute(f"INSERT INTO orders ({cols}) VALUES ({marks})", tuple(args.values()))
    conn.commit()
    oid = cur.lastrowid
    conn.close()
    assert oid is not None
    return oid


def _insert_trade(env, **over) -> int:
    args = {
        "amount": "10",
        "price": "0.001",
        "total": "0.01",
        "buyer_address": BUYER_AIT,
        "seller_address": SELLER_AIT,
        "fee_ait": "0.05",
        "buy_order_id": None,
        "sell_order_id": None,
        "settlement_state": "locked",
    }
    args.update(over)
    conn = _exdb(env)
    cols = ", ".join(args)
    marks = ", ".join("?" for _ in args)
    cur = conn.execute(f"INSERT INTO trades ({cols}) VALUES ({marks})", tuple(args.values()))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    assert tid is not None
    return tid


def _lock_tx(order_id, tx_hash: str, sender: str, units: int, sealed: bool = True) -> dict[str, Any]:
    return {
        "tx_hash": tx_hash,
        "sender": sender,
        "recipient": None,  # filled by the caller with the escrow address
        "value": units,
        "block_height": 600 if sealed else None,
        "payload": {"sell_quote": order_id},
        "nonce": 0,
    }


_TRADE_INSERT_KEYS = {
    "buy_order_id",
    "sell_order_id",
    "buyer_address",
    "seller_address",
    "seller_eth_address",
    "amount_ait",
    "eth_amount",
    "fee_ait",
}
_TRADE_UPDATE_KEYS = {
    "eth_tx_hash",
    "release_nonce",
    "settle_ait_tx_hash",
    "settle_fee_tx_hash",
    "refund_tx_hash",
    "escrow_out_nonce",
    "escrow_out_tx",
    "error",
}


def _trade_row(ref_id: int = 1, **over) -> dict[str, Any]:
    """Insert a real 'trade' settlement row (defaults: 10 AIT / 0.001 ETH /
    0.05 fee, buyer+seller fixtures) then push it to the requested status —
    the driver handlers only ever act on persisted rows."""
    insert_kwargs = {k: over.pop(k) for k in list(over) if k in _TRADE_INSERT_KEYS}
    insert_kwargs.setdefault("buy_order_id", 10)
    insert_kwargs.setdefault("sell_order_id", 20)
    insert_kwargs.setdefault("buyer_address", BUYER_AIT)
    insert_kwargs.setdefault("seller_address", SELLER_AIT)
    insert_kwargs.setdefault("seller_eth_address", SELLER_ETH)
    insert_kwargs.setdefault("amount_ait", Decimal("10"))
    insert_kwargs.setdefault("eth_amount", Decimal("0.001"))
    insert_kwargs.setdefault("fee_ait", Decimal("0.05"))
    status = over.pop("status", "locked")
    update_kwargs = {k: over.pop(k) for k in list(over) if k in _TRADE_UPDATE_KEYS}
    sid = insert_exchange_settlement("trade", ref_id, **insert_kwargs)
    assert sid
    if status != "locked" or update_kwargs:
        update_exchange_settlement(sid, status, **update_kwargs)
    row = get_exchange_settlement("trade", ref_id)
    assert row is not None
    return row


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_exchange_order_id_parsing(self):
        assert esm._exchange_order_id(42) == 42
        assert esm._exchange_order_id("42") == 42
        assert esm._exchange_order_id("sellq_abcdef") is None
        assert esm._exchange_order_id(True) is None
        assert esm._exchange_order_id(None) is None
        assert esm._exchange_order_id("0x42") is None
        assert esm._exchange_order_id(4.2) is None

    def test_units_to_ticks_floors(self):
        # 1 AIT = 36e6 units = 1e8 ticks exactly.
        assert esm._units_to_ticks(36_000_000) == 100_000_000
        # A fractional tick can never round the cover upward.
        assert esm._units_to_ticks(36_000_001) == 100_000_002
        assert esm._units_to_ticks(35_999_999) == 99_999_997
        assert esm._units_to_ticks(0) == 0

    def test_mirror_path_bfs(self):
        assert esm._mirror_path("locked", "settling") == ["releasing", "released", "settling"]
        assert esm._mirror_path("locked", "refunded") == ["releasing", "refund_pending", "refunding", "refunded"]
        assert esm._mirror_path("locked", "locked") == []
        assert esm._mirror_path("settled", "refunded") is None  # terminal — no path
        assert esm._mirror_path("released", "releasing") is None  # backwards — no path

    def test_mirror_map_parity(self):
        """The wallet-side replay map must match the endpoint's forward map
        — drift would replay a path the mirror then refuses."""
        from apps.exchange.simple_exchange.handlers.exchange import _TRADE_STATE_FORWARD

        assert esm._MIRROR_FORWARD == _TRADE_STATE_FORWARD

    def test_norm_tx_hash(self):
        """Gap 4: hash equality is spelling-insensitive — case and the 0x
        prefix never change which chain artifact is meant."""
        assert esm._norm_tx_hash("0xDeAdBeEf") == "deadbeef"
        assert esm._norm_tx_hash("deadbeef") == "deadbeef"
        assert esm._norm_tx_hash("0XAB12") == "ab12"
        assert esm._norm_tx_hash(None) == "" and esm._norm_tx_hash("") == ""

    def test_lock_refund_ref_id_range(self):
        """Squat fix: the fallback ref_id is deterministic per lock, bounded
        below −2**59, and disjoint from every ±order_id / trade id — no
        reader can mistake it for an order id."""
        for h in ("0xdeadbeef", "0x" + "0" * 14 + "1", "0x" + "f" * 15, "0x1234", "0x" + "a" * 64):
            rid = esm._lock_refund_ref_id(h)
            assert -(1 << 60) <= rid <= -(1 << 59), (h, rid)
        # Case/prefix respellings of one lock derive the same id (dedup-safe).
        assert esm._lock_refund_ref_id("0xDeAdBeEf") == esm._lock_refund_ref_id("deadbeef")
        # Far below any plausible order id — never confusable with ±order_id.
        assert esm._lock_refund_ref_id("0x1234") < -(1 << 59) < -(2**31)


# ---------------------------------------------------------------------------
# Lane 1 — escrow lock scan
# ---------------------------------------------------------------------------


class TestLockScan:
    @pytest.mark.asyncio
    async def test_fresh_lock_posts_order_funded(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        lock = _lock_tx(oid, "0xlock1", SELLER_AIT, 3_636_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["funded"] == 1
        post = exchange_env["posts"][-1]
        assert post["event"] == "order_funded" and post["order_id"] == oid
        assert post["backing_tx_hash"] == "0xlock1" and post["head"] == 1000
        # 3.636e9 units = 101 AIT -> 101e8 ticks exactly.
        assert post["locked_ticks"] == 10_100_000_000
        mark = monitor_mark("lock:0xlock1")
        assert mark is not None and mark["outcome"] == "funded"

    @pytest.mark.asyncio
    async def test_marked_lock_is_not_reposted(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, funded_state="unfunded")
        lock = _lock_tx(oid, "0xlock2", SELLER_AIT, 360_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        await esm._scan_order_locks(cfg, head=1000)
        await esm._scan_order_locks(cfg, head=1000)
        funded_posts = [p for p in exchange_env["posts"] if p["event"] == "order_funded"]
        assert len(funded_posts) == 1

    @pytest.mark.asyncio
    async def test_lock_on_taken_order_creates_order_refund(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(
            exchange_env,
            funded_state="funded",
            backing_tx_hash="0xfirst",
            locked_ticks=1_000_000_000,
        )
        stray = _lock_tx(oid, "0xsecond", "0x6666666666666666666666666666666666666666", 72_000_000)
        stray["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(stray)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        # Inbound-lock refunds key on −order_id so they never squat the
        # owner's +order_id remainder-refund row (ETH-JOIN fixup).
        row = get_exchange_settlement("order_refund", -oid)
        assert row is not None and row["status"] == "locked"
        # The refund targets the lock's sender, not the order owner.
        assert row["seller_address"] == "0x6666666666666666666666666666666666666666"
        assert Decimal(str(row["amount_ait"])) == Decimal("2")
        assert monitor_mark("lock:0xsecond")["outcome"] == "refunding"

    @pytest.mark.asyncio
    async def test_sellq_locks_are_ignored(self, exchange_env):
        cfg = _cfg(exchange_env)
        tx = _lock_tx(None, "0xsellq", SELLER_AIT, 36_000_000)
        tx["recipient"] = exchange_env["escrow"]
        tx["payload"] = {"sell_quote": "sellq_abc123"}
        exchange_env["transfers"].append(tx)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["scanned"] == 0 and stats["funded"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [401, 403, 500, 503])
    async def test_refused_order_funded_is_unmarked_and_retried(self, exchange_env, status_code):
        """A non-terminal refusal (5xx/401/403/flag-off 503) must never mark
        the lock — marking would strand escrowed AIT with no refund row. The
        poll counts it under http_refused and retries next poll; a recovered
        endpoint still funds the same lock."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        lock = _lock_tx(oid, "0xhttpfail", SELLER_AIT, 3_636_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        exchange_env["post_responses"]["order_funded"] = (status_code, {"error": "refused"})
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["http_refused"] == 1 and stats["funded"] == 0
        assert monitor_mark("lock:0xhttpfail") is None
        assert get_exchange_settlement("order_refund", oid) is None
        assert get_exchange_settlement("order_refund", -oid) is None
        # Next poll hits a recovered endpoint → the same lock funds.
        exchange_env["post_responses"].pop("order_funded")
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["funded"] == 1
        assert monitor_mark("lock:0xhttpfail")["outcome"] == "funded"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [404, 409])
    async def test_terminal_refusal_still_refunds_and_marks(self, exchange_env, status_code):
        """404 (order gone) / 409 (lock under cover) stay terminal: the lock
        is refunded to its sender (ref_id −oid) and marked."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        lock = _lock_tx(oid, f"0xgone{status_code}", SELLER_AIT, 72_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        exchange_env["post_responses"]["order_funded"] = (status_code, {"error": "terminal"})
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        assert monitor_mark(f"lock:0xgone{status_code}")["outcome"] == "refunding"
        row = get_exchange_settlement("order_refund", -oid)
        assert row is not None and row["seller_address"] == SELLER_AIT

    @pytest.mark.asyncio
    async def test_recorded_reobserve_normalizes_hash_spelling(self, exchange_env):
        """Gap 4: the funded lock re-observed on later polls matches
        backing_tx_hash independent of case/prefix — a spelling change must
        not drop it into the refund lane and sweep the order's backing."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(
            exchange_env,
            order_type="SELL",
            status="open",
            funded_state="funded",
            backing_tx_hash="0xDeAdBeEf",
            locked_ticks=1_000_000_000,
        )
        lock = _lock_tx(oid, "0xdeadbeef", SELLER_AIT, 36_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 0
        assert monitor_mark("lock:0xdeadbeef")["outcome"] == "recorded"
        assert get_exchange_settlement("order_refund", -oid) is None

    @pytest.mark.asyncio
    async def test_owner_under_cover_refund_survives_stranger_squat(self, exchange_env):
        """Squat residual: a stranger's dust lock holds −order_id, then the
        owner's own under-cover lock still gets its refund — keyed on a
        lock-hash ref_id below −2**59. A second stranger lock afterwards
        stays 'duplicate' (the one-per-order bound for non-owners)."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        for tx_hash, sender in (("0x0bb1", stranger), ("0x0aa1", SELLER_AIT)):
            lock = _lock_tx(oid, tx_hash, sender, 36_000_000)
            lock["recipient"] = exchange_env["escrow"]
            exchange_env["transfers"].append(lock)
        exchange_env["post_responses"]["order_funded"] = (409, {"error": "lock under cover"})
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 2
        # −oid still belongs to the stranger's dust refund.
        stray_row = get_exchange_settlement("order_refund", -oid)
        assert stray_row is not None and stray_row["seller_address"] == stranger
        # The owner's refund landed on the deterministic lock-keyed ref_id.
        lock_ref = esm._lock_refund_ref_id("0x0aa1")
        assert lock_ref < -(1 << 59)
        owner_row = get_exchange_settlement("order_refund", lock_ref)
        assert owner_row is not None and owner_row["seller_address"] == SELLER_AIT
        assert monitor_mark("lock:0x0aa1")["outcome"] == "refunding"
        # A second stranger lock stays a logged duplicate — bound unchanged.
        extra = _lock_tx(oid, "0x0cc1", stranger, 36_000_000)
        extra["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(extra)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 0
        assert monitor_mark("lock:0x0cc1")["outcome"] == "duplicate"
        # Re-polling creates no new rows — marks dedupe every lock.
        conn = bridge_db._connect_db()
        n_rows = conn.execute("SELECT COUNT(*) FROM exchange_settlements").fetchone()[0]
        conn.close()
        await esm._scan_order_locks(cfg, head=1000)
        conn = bridge_db._connect_db()
        assert conn.execute("SELECT COUNT(*) FROM exchange_settlements").fetchone()[0] == n_rows
        conn.close()

    @pytest.mark.asyncio
    async def test_below_fee_stranger_lock_creates_no_row(self, exchange_env):
        """ETH-JOIN-3: a stranger's lock at/below the sweep fee is worth
        less than its refund — no order_refund row, no mark; the re-scan
        just re-evaluates it."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(
            exchange_env,
            funded_state="funded",
            backing_tx_hash="0xfirst",
            locked_ticks=1_000_000_000,
        )
        dust = _lock_tx(oid, "0xdust1", stranger, 36_000)  # 0.001 AIT < 0.01 fee
        dust["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(dust)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 0
        assert get_exchange_settlement("order_refund", -oid) is None
        assert monitor_mark("lock:0xdust1") is None

    @pytest.mark.asyncio
    async def test_below_fee_owner_lock_no_row_on_either_insert(self, exchange_env):
        """A sub-fee owner lock must not get the -order_id row OR the
        lock-keyed fallback — the check precedes both inserts even when
        the -order_id slot is already held."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        # Hold the -order_id slot so a missing bound would try the fallback.
        insert_exchange_settlement(
            "order_refund",
            -oid,
            seller_address="0x6666666666666666666666666666666666666666",
            amount_ait=Decimal("1"),
            fee_ait=Decimal(0),
        )
        dust = _lock_tx(oid, "0xdust2", SELLER_AIT, 36_000)
        dust["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(dust)
        exchange_env["post_responses"]["order_funded"] = (409, {"error": "lock under cover"})
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 0
        conn = bridge_db._connect_db()
        assert conn.execute("SELECT COUNT(*) FROM exchange_settlements").fetchone()[0] == 1
        conn.close()
        assert monitor_mark("lock:0xdust2") is None

    @pytest.mark.asyncio
    async def test_just_above_fee_owner_lock_still_uses_fallback(self, exchange_env):
        """The bound is at the fee, not above it: an owner lock barely over
        the sweep fee whose -order_id slot is held still refunds via the
        lock-keyed fallback."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        insert_exchange_settlement(
            "order_refund",
            -oid,
            seller_address="0x6666666666666666666666666666666666666666",
            amount_ait=Decimal("1"),
            fee_ait=Decimal(0),
        )
        lock = _lock_tx(oid, "0x0aa2", SELLER_AIT, 720_000)  # 0.02 AIT > 0.01 fee
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        exchange_env["post_responses"]["order_funded"] = (409, {"error": "lock under cover"})
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        owner_row = get_exchange_settlement("order_refund", esm._lock_refund_ref_id("0x0aa2"))
        assert owner_row is not None and owner_row["seller_address"] == SELLER_AIT
        assert monitor_mark("lock:0x0aa2")["outcome"] == "refunding"

    @pytest.mark.asyncio
    async def test_just_above_fee_stranger_lock_gets_row(self, exchange_env):
        """A stranger above the fee still gets the -order_id refund row —
        the bound only removes sub-fee refunds, not the refund itself."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(
            exchange_env,
            funded_state="funded",
            backing_tx_hash="0xfirst",
            locked_ticks=1_000_000_000,
        )
        lock = _lock_tx(oid, "0xstray9", stranger, 720_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        row = get_exchange_settlement("order_refund", -oid)
        assert row is not None and row["seller_address"] == stranger
        assert monitor_mark("lock:0xstray9")["outcome"] == "refunding"

    @pytest.mark.asyncio
    async def test_below_fee_follows_sweep_fee_accessor(self, exchange_env, monkeypatch):
        """The inbound skip reads _sweep_fee_ait() — the same accessor as
        the remainder skip — so both bounds move together if the fee
        source ever changes."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(
            exchange_env,
            funded_state="funded",
            backing_tx_hash="0xfirst",
            locked_ticks=1_000_000_000,
        )
        lock = _lock_tx(oid, "0xdust3", stranger, 72_000_000)  # 2 AIT
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        monkeypatch.setattr(esm, "_sweep_fee_ait", lambda: Decimal("5"))
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 0
        assert monitor_mark("lock:0xdust3") is None
        monkeypatch.setattr(esm, "_sweep_fee_ait", lambda: Decimal("0.01"))
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        assert get_exchange_settlement("order_refund", -oid) is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_hash", ["", "0xZZZZ", None])
    async def test_bad_tx_hash_fallback_returns_bad_tx_hash(self, exchange_env, bad_hash, caplog):
        """Empty/non-hex/None input on the owner-fallback attempt returns
        bad_tx_hash, writes no row, and logs ERROR naming the hash
        problem — never a ref_id collision."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        insert_exchange_settlement(
            "order_refund",
            -oid,
            seller_address="0x6666666666666666666666666666666666666666",
            amount_ait=Decimal("1"),
            fee_ait=Decimal(0),
        )
        with caplog.at_level(logging.ERROR):
            outcome = await esm._ensure_order_refund(
                cfg, oid, SELLER_AIT, Decimal("1"), bad_hash, remainder=False, owner_lock=True
            )
        assert outcome == "bad_tx_hash"
        assert any("empty or not hex" in r.getMessage() for r in caplog.records)
        conn = bridge_db._connect_db()
        assert conn.execute("SELECT COUNT(*) FROM exchange_settlements").fetchone()[0] == 1
        conn.close()

    @pytest.mark.asyncio
    async def test_bad_tx_hash_marks_like_duplicate(self, exchange_env):
        """Through the scan, bad_tx_hash marks the lock exactly like a
        duplicate — terminal, no retry, no row."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        insert_exchange_settlement(
            "order_refund",
            -oid,
            seller_address="0x6666666666666666666666666666666666666666",
            amount_ait=Decimal("1"),
            fee_ait=Decimal(0),
        )
        lock = _lock_tx(oid, "0xzzzz", SELLER_AIT, 72_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        exchange_env["post_responses"]["order_funded"] = (409, {"error": "lock under cover"})
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 0
        assert monitor_mark("lock:0xzzzz")["outcome"] == "bad_tx_hash"

    def test_below_fee_log_rate_limited_per_lock(self, caplog):
        """INFO once per lock per hour, DEBUG between — a permanent dust
        lock re-evaluated every poll must not spam the journal."""
        esm._below_fee_last_log.clear()
        h = "0x" + "ab" * 32
        with caplog.at_level(logging.DEBUG):
            esm._log_below_fee(7, h, Decimal("0.001"))
            esm._log_below_fee(7, h, Decimal("0.001"))
        infos = [r for r in caplog.records if r.levelno == logging.INFO]
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(infos) == 1 and "lock value cannot cover the refund sweep fee — no row" in infos[0].getMessage()
        assert len(debugs) == 1
        esm._below_fee_last_log[h] -= esm._BELOW_FEE_LOG_SECONDS + 1
        caplog.clear()
        with caplog.at_level(logging.INFO):
            esm._log_below_fee(7, h, Decimal("0.001"))
        assert any(r.levelno == logging.INFO for r in caplog.records)


# ---------------------------------------------------------------------------
# Lane 2 — prepay deposit scan
# ---------------------------------------------------------------------------


class TestPrepayScan:
    @pytest.mark.asyncio
    async def test_exchange_prepay_posts_credit(self, exchange_env):
        cfg = _cfg(exchange_env)
        insert_exchange_prepay_deposit("0xdep1", "0xfrom", Decimal("0.01"), SELLER_AIT.lower())
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["credited"] == 1
        post = exchange_env["posts"][-1]
        assert post["event"] == "prepaid_credit" and post["eth_tx_hash"] == "0xdep1"
        # The raw tag text goes to the endpoint as-typed — it canonicalizes.
        assert post["node_address"] == SELLER_AIT.lower()
        assert monitor_mark("credit:0xdep1")["outcome"] == "credited"

    @pytest.mark.asyncio
    async def test_409_marks_unattributable_once(self, exchange_env):
        cfg = _cfg(exchange_env)
        exchange_env["post_responses"]["prepaid_credit"] = (409, {"error": "node not registered"})
        insert_exchange_prepay_deposit("0xdep2", "0xfrom", Decimal("0.01"), SELLER_AIT)
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["unattributable"] == 1
        # A second poll does not repost.
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["unattributable"] == 0
        assert len([p for p in exchange_env["posts"] if p["event"] == "prepaid_credit"]) == 1

    @pytest.mark.asyncio
    async def test_400_marked_rejected_not_retried(self, exchange_env):
        cfg = _cfg(exchange_env)
        exchange_env["post_responses"]["prepaid_credit"] = (400, {"error": "bad address"})
        insert_exchange_prepay_deposit("0xdep3", "0xfrom", Decimal("0.01"), "not-an-address")
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["rejected"] == 1
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["rejected"] == 0

    @pytest.mark.asyncio
    async def test_transport_failure_retries_next_poll(self, exchange_env):
        cfg = _cfg(exchange_env)
        insert_exchange_prepay_deposit("0xdep4", "0xfrom", Decimal("0.01"), SELLER_AIT)

        async def _boom(cfg, payload):
            raise RuntimeError("connection refused")

        with patch("wallet_app.bridge.exchange_settlement_monitor._post_event", _boom):
            stats = await esm._scan_prepay_credits(cfg)
            assert stats["credited"] == 0
        # Unmarked — next poll posts again.
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["credited"] == 1

    @pytest.mark.asyncio
    async def test_normal_deposits_are_untouched(self, exchange_env):
        """Only 'exchange_prepay' rows feed the lane — a plain 'pending'
        deposit (the payout path's) must never be read here."""
        cfg = _cfg(exchange_env)
        bridge_db.insert_deposit("0xplain", "0xfrom", Decimal("0.5"), Decimal("100"), recipient=BUYER_AIT)
        stats = await esm._scan_prepay_credits(cfg)
        assert stats["scanned"] == 0
        assert exchange_env["posts"] == []


# ---------------------------------------------------------------------------
# Lane 3 — backing expiry / stranded debit / lock remainder
# ---------------------------------------------------------------------------


class TestBackingScan:
    @pytest.mark.asyncio
    async def test_expired_open_order_posts_backing_expired(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, funded_state="funded", expiry_height=999)
        await esm._scan_backing(cfg, head=1000)
        assert exchange_env["posts"][-1] == {"event": "order_backing_expired", "order_id": oid}

    @pytest.mark.asyncio
    async def test_unexpired_order_is_quiet(self, exchange_env):
        cfg = _cfg(exchange_env)
        _insert_order(exchange_env, funded_state="funded", expiry_height=5000)
        await esm._scan_backing(cfg, head=1000)
        assert [p for p in exchange_env["posts"] if p["event"] == "order_backing_expired"] == []

    @pytest.mark.asyncio
    async def test_stranded_buy_debit_posts_refund(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="BUY", status="cancelled", funded_state="funded")
        conn = _exdb(exchange_env)
        conn.execute(
            "INSERT INTO prepaid_debits (node_address, order_id, amount_eth, committed_eth, state) "
            "VALUES (?, ?, ?, '0', 'open')",
            (BUYER_AIT, oid, "0.01"),
        )
        conn.commit()
        conn.close()
        await esm._scan_backing(cfg, head=1000)
        assert {"event": "debit_refund", "order_id": oid} in exchange_env["posts"]

    @pytest.mark.asyncio
    async def test_expired_funded_sell_refunds_lock_remainder(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(
            exchange_env,
            status="expired",
            funded_state="backing_expired",
            backing_tx_hash="0xback",
            locked_ticks=1_500_000_000,  # 15 AIT locked
        )
        # One 10-AIT trade drew amount+fee=10.05 from the lock.
        _insert_trade(
            exchange_env,
            amount="10",
            fee_ait="0.05",
            sell_order_id=oid,
            settlement_state="settled",
        )
        sender = "0x6666666666666666666666666666666666666666"
        back = {
            "tx_hash": "0xback",
            "sender": sender,
            "recipient": exchange_env["escrow"],
            "value": 540_000_000,
            "block_height": 500,
            "payload": {"sell_quote": oid},
        }
        exchange_env["transfers"].append(back)
        stats = await esm._scan_backing(cfg, head=1000)
        assert stats["refunds"] == 1
        row = get_exchange_settlement("order_refund", oid)
        # Remainder = 15 − 10.05 = 4.95 AIT back to the lock sender.
        assert row is not None
        assert Decimal(str(row["amount_ait"])) == Decimal("4.95")
        assert row["seller_address"] == sender

    @pytest.mark.asyncio
    async def test_remainder_refund_waits_for_live_settlements(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(
            exchange_env,
            status="expired",
            funded_state="backing_expired",
            backing_tx_hash="0xback",
            locked_ticks=1_500_000_000,
        )
        _insert_trade(exchange_env, amount="10", fee_ait="0.05", sell_order_id=oid, settlement_state="releasing")
        stats = await esm._scan_backing(cfg, head=1000)
        assert stats["refunds"] == 0
        assert get_exchange_settlement("order_refund", oid) is None

    @pytest.mark.asyncio
    async def test_stray_lock_never_blocks_owner_remainder_refund(self, exchange_env):
        """ETH-JOIN gap 2: a stranger's dust lock refunds under ref_id −oid,
        so it cannot squat the owner's +oid lock-remainder refund row."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        stray = _lock_tx(oid, "0xstray", stranger, 36_000_000)
        stray["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(stray)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        assert get_exchange_settlement("order_refund", -oid) is not None
        assert get_exchange_settlement("order_refund", oid) is None
        # The owner then funds, fills once (10 AIT + 0.05 fee), and the order
        # is cancelled — 15 − 10.05 = 4.95 AIT of backing is stranded.
        conn = _exdb(exchange_env)
        conn.execute(
            "UPDATE orders SET status = 'cancelled', funded_state = 'funded', "
            "backing_tx_hash = '0xback', locked_ticks = 1500000000 WHERE id = ?",
            (oid,),
        )
        conn.commit()
        conn.close()
        _insert_trade(exchange_env, amount="10", fee_ait="0.05", sell_order_id=oid, settlement_state="settled")
        exchange_env["transfers"].append(
            {
                "tx_hash": "0xback",
                "sender": SELLER_AIT,
                "recipient": exchange_env["escrow"],
                "value": 540_000_000,
                "block_height": 500,
                "payload": {"sell_quote": oid},
            }
        )
        stats = await esm._scan_backing(cfg, head=1000)
        assert stats["refunds"] == 1
        row = get_exchange_settlement("order_refund", oid)
        assert row is not None
        assert row["seller_address"] == SELLER_AIT
        assert Decimal(str(row["amount_ait"])) == Decimal("4.95")

    @pytest.mark.asyncio
    async def test_second_stray_lock_logs_duplicate_not_second_refund(self, exchange_env, caplog):
        """The UNIQUE pair still bounds inbound refunds to one per order — a
        second stray is logged for the operator and never a second row."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        for tx_hash in ("0xstray1", "0xstray2"):
            lock = _lock_tx(oid, tx_hash, stranger, 36_000_000)
            lock["recipient"] = exchange_env["escrow"]
            exchange_env["transfers"].append(lock)
        with caplog.at_level(logging.ERROR):
            stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["refunds"] == 1
        assert monitor_mark("lock:0xstray1")["outcome"] == "refunding"
        assert monitor_mark("lock:0xstray2")["outcome"] == "duplicate"
        assert any("second stray lock" in r.getMessage() for r in caplog.records)
        assert get_exchange_settlement("order_refund", -oid) is not None
        assert get_exchange_settlement("order_refund", oid) is None

    @pytest.mark.asyncio
    async def test_lock_sender_normalizes_hash_spelling(self, exchange_env):
        """Gap 4: _lock_sender must find the recorded lock when the RPC
        respells its hash — otherwise the remainder refund falls back to
        the order owner and pays the wrong account."""
        cfg = _cfg(exchange_env)
        stranger = "0x6666666666666666666666666666666666666666"
        oid = _insert_order(
            exchange_env,
            status="cancelled",
            funded_state="funded",
            backing_tx_hash="0xABCDEF00",  # order row respelled vs the chain row
            locked_ticks=1_000_000_000,
        )
        exchange_env["transfers"].append(
            {
                "tx_hash": "0xabcdef00",
                "sender": stranger,
                "recipient": exchange_env["escrow"],
                "value": 360_000_000,
                "block_height": 500,
                "payload": {"sell_quote": oid},
            }
        )
        stats = await esm._scan_backing(cfg, head=1000)
        assert stats["refunds"] == 1
        row = get_exchange_settlement("order_refund", oid)
        assert row is not None and row["seller_address"] == stranger  # not the order owner


# ---------------------------------------------------------------------------
# Trade-row ensure + mirror
# ---------------------------------------------------------------------------


class TestTradeRows:
    def test_ensure_creates_denormalized_row(self, exchange_env):
        cfg = _cfg(exchange_env)
        buy_id = _insert_order(exchange_env, order_type="BUY", user_address=BUYER_AIT)
        sell_id = _insert_order(exchange_env, seller_eth_address=SELLER_ETH)
        tid = _insert_trade(exchange_env, buy_order_id=buy_id, sell_order_id=sell_id)
        stats = esm._ensure_trade_rows(cfg)
        assert stats["created"] == 1
        row = get_exchange_settlement("trade", tid)
        assert row is not None and row["status"] == "locked"
        assert row["buyer_address"] == BUYER_AIT
        assert row["seller_eth_address"] == SELLER_ETH
        assert Decimal(str(row["eth_amount"])) == Decimal("0.01")
        assert Decimal(str(row["fee_ait"])) == Decimal("0.05")
        # Idempotent — a second pass creates nothing.
        assert esm._ensure_trade_rows(cfg)["created"] == 0

    def test_terminal_mirror_gets_no_row(self, exchange_env):
        cfg = _cfg(exchange_env)
        _insert_trade(exchange_env, settlement_state="settled", buy_order_id=1, sell_order_id=2)
        assert esm._ensure_trade_rows(cfg)["created"] == 0

    def test_unlinked_trade_marks_terminal_once(self, exchange_env, caplog):
        """Gap 6: a trade with NULL order links gets one ERROR and a terminal
        monitor mark — no settlement row, no ERROR on later polls."""
        cfg = _cfg(exchange_env)
        tid = _insert_trade(exchange_env, buy_order_id=None, sell_order_id=None)
        with caplog.at_level(logging.ERROR):
            stats = esm._ensure_trade_rows(cfg)
            stats2 = esm._ensure_trade_rows(cfg)
        assert stats["created"] == 0 and stats2["created"] == 0
        errs = [r for r in caplog.records if r.levelno >= logging.ERROR and str(tid) in r.getMessage()]
        assert len(errs) == 1
        mark = monitor_mark(f"unlinked-trade:{tid}")
        assert mark is not None and mark["outcome"] == "no_order_links"
        assert get_exchange_settlement("trade", tid) is None

    def test_no_payout_trade_skips_counts_and_self_heals(self, exchange_env, caplog):
        """Gap 5: no resolvable payout address skips the row without a mark —
        counted in the stats, ERROR rate-limited to once per hour, and the
        trade settles on its own once a payout address appears."""
        cfg = _cfg(exchange_env)
        buy_id = _insert_order(exchange_env, order_type="BUY", user_address=BUYER_AIT)
        sell_id = _insert_order(exchange_env, seller_eth_address=None)
        tid = _insert_trade(exchange_env, buy_order_id=buy_id, sell_order_id=sell_id)
        esm._no_payout_last_log.clear()
        with caplog.at_level(logging.DEBUG):
            stats = esm._ensure_trade_rows(cfg)
            stats2 = esm._ensure_trade_rows(cfg)
        assert stats["created"] == 0 and stats["no_payout_skipped"] == 1
        assert stats2["created"] == 0 and stats2["no_payout_skipped"] == 1
        assert get_exchange_settlement("trade", tid) is None
        errs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errs) == 1  # only the first poll logs ERROR
        assert any(r.levelno == logging.DEBUG for r in caplog.records)
        # A payout address appearing later heals it — next poll creates the row.
        conn = _exdb(exchange_env)
        conn.execute("UPDATE orders SET seller_eth_address = ? WHERE id = ?", (SELLER_ETH, sell_id))
        conn.commit()
        conn.close()
        stats3 = esm._ensure_trade_rows(cfg)
        assert stats3["created"] == 1 and stats3["no_payout_skipped"] == 0
        assert get_exchange_settlement("trade", tid)["seller_eth_address"] == SELLER_ETH

    @pytest.mark.asyncio
    async def test_poll_summary_counts_no_payout_skips(self, exchange_env):
        buy_id = _insert_order(exchange_env, order_type="BUY", user_address=BUYER_AIT)
        sell_id = _insert_order(exchange_env, seller_eth_address=None)
        _insert_trade(exchange_env, buy_order_id=buy_id, sell_order_id=sell_id)
        summary = await esm.poll_exchange_settlements_once()
        assert summary["no_payout_skipped"] == 1
        assert summary["new_rows"] == {"created": 0}

    @pytest.mark.asyncio
    async def test_mirror_replays_missed_states_after_restart(self, exchange_env):
        """Ledger at 'settling' while the mirror is still 'locked' — the
        pass must post the intermediate states in order (the endpoint's
        forward-only map refuses skips)."""
        cfg = _cfg(exchange_env)
        tid = _insert_trade(exchange_env, settlement_state="locked")
        sid = insert_exchange_settlement("trade", tid, amount_ait=Decimal("10"), eth_amount=Decimal("0.01"))
        update_exchange_settlement(sid, "settling", escrow_out_nonce=3, escrow_out_tx="{}")
        await esm._mirror_pass(cfg)
        states = [p["state"] for p in exchange_env["posts"] if p["event"] == "trade_state"]
        assert states == ["releasing", "released", "settling"]

    @pytest.mark.asyncio
    async def test_mirror_409_never_blocks_ledger(self, exchange_env):
        cfg = _cfg(exchange_env)
        tid = _insert_trade(exchange_env, settlement_state="locked")
        sid = insert_exchange_settlement("trade", tid)
        update_exchange_settlement(sid, "releasing")
        exchange_env["post_responses"]["trade_state"] = (409, {"error": "cannot move"})
        await esm._mirror_pass(cfg)  # must not raise
        assert get_exchange_settlement("trade", tid)["status"] == "releasing"

    @pytest.mark.asyncio
    async def test_mirror_posts_hashes_on_settled(self, exchange_env):
        cfg = _cfg(exchange_env)
        tid = _insert_trade(exchange_env, settlement_state="settling")
        sid = insert_exchange_settlement("trade", tid)
        update_exchange_settlement(
            sid,
            "settled",
            eth_tx_hash="0xeth",
            settle_ait_tx_hash="0xait",
            settle_fee_tx_hash="0xfee",
        )
        await esm._mirror_pass(cfg)
        post = [p for p in exchange_env["posts"] if p["event"] == "trade_state"][-1]
        assert post["state"] == "settled"
        assert post["eth_tx_hash"] == "0xeth" and post["ait_tx_hash"] == "0xait" and post["fee_tx_hash"] == "0xfee"


# ---------------------------------------------------------------------------
# Trade driver — status handlers
# ---------------------------------------------------------------------------


class TestDriver:
    @pytest.mark.asyncio
    async def test_locked_releases_eth_intent_first(self, exchange_env):
        cfg = _cfg(exchange_env)
        row = _trade_row()
        await esm._handle_locked(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        # The intent (hash + nonce) persisted and the broadcast happened
        # (the stub recorded it).
        assert fresh["status"] == "releasing"
        assert fresh["eth_tx_hash"] and fresh["release_nonce"] == 7
        assert len(exchange_env["eth_sends"]) == 1
        assert fresh["id"] == row["id"]

    @pytest.mark.asyncio
    async def test_locked_parks_on_reserve_deficit(self, exchange_env):
        cfg = _cfg(exchange_env)
        exchange_env["eth_balance"] = Decimal("0.0001")
        row = _trade_row()
        await esm._handle_locked(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "queued_reserve"
        assert exchange_env["eth_sends"] == []

    @pytest.mark.asyncio
    async def test_missing_payout_parks_needs_review(self, exchange_env):
        cfg = _cfg(exchange_env)
        row = _trade_row(seller_eth_address=None)
        await esm._handle_locked(cfg, row)
        assert get_exchange_settlement("trade", 1)["status"] == "needs_review"

    @pytest.mark.asyncio
    async def test_releasing_confirmed_receipt_releases(self, exchange_env):
        cfg = _cfg(exchange_env)
        exchange_env["receipts"]["0xeth1"] = {"status": "0x1", "blockNumber": "0x100"}
        exchange_env["nonces"]["latest"] = 8
        row = _trade_row(status="releasing", eth_tx_hash="0xeth1", release_nonce=7)
        await esm._handle_inflight(cfg, row)
        assert get_exchange_settlement("trade", 1)["status"] == "released"

    @pytest.mark.asyncio
    async def test_releasing_proven_unsent_refunds(self, exchange_env):
        cfg = _cfg(exchange_env)
        # Receipt says the recorded hash reverted — proven not sent.
        exchange_env["receipts"]["0xeth1"] = {"status": "0x0", "blockNumber": "0x100"}
        row = _trade_row(status="releasing", eth_tx_hash="0xeth1", release_nonce=7)
        await esm._handle_inflight(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "refunding"
        assert fresh["escrow_out_nonce"] == 0  # the refund sweep's intent
        assert len(exchange_env["ait_sends"]) == 1
        # The refund leg: amount+fee back to the seller (AIT address).
        sent = exchange_env["ait_sends"][0]
        assert sent["payload"]["exs_ref"] == row["id"]

    @pytest.mark.asyncio
    async def test_released_starts_settle_leg1(self, exchange_env):
        cfg = _cfg(exchange_env)
        exchange_env["receipts"]["0xeth1"] = {"status": "0x1", "blockNumber": "0x100"}
        exchange_env["nonces"]["latest"] = 8
        row = _trade_row(status="released", eth_tx_hash="0xeth1", release_nonce=7)
        await esm._handle_released(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "settling"
        assert fresh["escrow_out_nonce"] == 0 and fresh["escrow_out_tx"]
        # Leg 1 = amount → buyer, tagged exs_ref.
        sent = exchange_env["ait_sends"][0]
        assert sent["payload"]["exs_ref"] == row["id"]

    @pytest.mark.asyncio
    async def test_settling_leg1_seal_broadcasts_leg2(self, exchange_env):
        cfg = _cfg(exchange_env)
        row = _trade_row(status="settling", escrow_out_nonce=3, escrow_out_tx="{}")
        # The sealed leg-1 outflow: amount→buyer at escrow nonce 3.
        leg1 = {
            "tx_hash": "0xleg1",
            "sender": exchange_env["escrow"],
            "recipient": BUYER_AIT,
            "value": 360_000_000,  # 10 AIT in chain units
            "block_height": 610,
            "nonce": 3,
            "payload": {"exs_ref": row["id"], "reason": "settling"},
        }
        exchange_env["transfers"].append(leg1)
        exchange_env["escrow_nonce"] = 4  # leg1 consumed nonce 3; next free is 4
        await esm._resolve_sweep(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "settling"  # leg 2 now in flight
        assert fresh["settle_ait_tx_hash"] == "0xleg1"
        assert fresh["escrow_out_nonce"] == 4  # leg2's intent overwrote leg1's
        leg2 = exchange_env["ait_sends"][-1]
        assert leg2["payload"]["reason"] == "settle_fee"
        assert leg2["payload"]["exs_ref"] == row["id"]

    @pytest.mark.asyncio
    async def test_settling_leg2_seal_settles(self, exchange_env):
        cfg = _cfg(exchange_env)
        row = _trade_row(
            status="settling",
            settle_ait_tx_hash="0xleg1",
            escrow_out_nonce=4,
            escrow_out_tx="{}",
        )
        leg2 = {
            "tx_hash": "0xleg2",
            "sender": exchange_env["escrow"],
            "recipient": TEST_TREASURY,
            "value": 1_800_000,  # 0.05 AIT fee in chain units
            "block_height": 611,
            "nonce": 4,
            "payload": {"exs_ref": row["id"], "reason": "settle_fee"},
        }
        exchange_env["transfers"].append(leg2)
        await esm._resolve_sweep(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "settled"
        assert fresh["settle_fee_tx_hash"] == "0xleg2"

    @pytest.mark.asyncio
    async def test_foreign_nonce_consumption_parks_sweep(self, exchange_env):
        cfg = _cfg(exchange_env)
        # Account nonce (4) has passed the intent nonce (3) but no matching
        # outflow is on chain — a foreign tx consumed it: undecidable.
        exchange_env["escrow_nonce"] = 4
        row = _trade_row(status="refunding", escrow_out_nonce=3, escrow_out_tx="{}")
        await esm._resolve_sweep(cfg, row)
        assert get_exchange_settlement("trade", 1)["status"] == "needs_review_sweep"

    @pytest.mark.asyncio
    async def test_unsealed_intent_rebroadcasts_stored_blob(self, exchange_env):
        cfg = _cfg(exchange_env)
        blob = {"signed": "yes"}
        row = _trade_row(status="refunding", escrow_out_nonce=3, escrow_out_tx=json.dumps(blob))
        await esm._resolve_sweep(cfg, row)
        assert exchange_env["ait_sends"][-1] == blob
        assert get_exchange_settlement("trade", 1)["status"] == "refunding"

    @pytest.mark.asyncio
    async def test_needs_review_sweep_is_parked(self, exchange_env):
        cfg = _cfg(exchange_env)
        row = _trade_row(status="needs_review_sweep")
        await esm._process_settlement(cfg, row)
        assert exchange_env["posts"] == [] and exchange_env["ait_sends"] == []

    @pytest.mark.asyncio
    async def test_inflight_sweep_serializes_lanes(self, exchange_env):
        """A sell-lane sweep in flight defers a released settle leg."""
        from wallet_app.bridge.bridge_db import insert_sell_lock, update_sell_lock_status

        sid = insert_sell_lock(
            ait_tx_hash="0xsell",
            shop_ait_address="0xsender",
            amount_ait=Decimal("1"),
            quote_id="sellq_x",
        )
        assert sid
        update_sell_lock_status("0xsell", "settling", escrow_out_nonce=1, escrow_out_tx="{}")
        cfg = _cfg(exchange_env)
        exchange_env["receipts"]["0xeth1"] = {"status": "0x1", "blockNumber": "0x100"}
        exchange_env["nonces"]["latest"] = 8
        row = _trade_row(status="released", eth_tx_hash="0xeth1", release_nonce=7)
        await esm._handle_released(cfg, row)
        # Deferred — still 'released', nothing broadcast.
        assert get_exchange_settlement("trade", 1)["status"] == "released"
        assert exchange_env["ait_sends"] == []


# ---------------------------------------------------------------------------
# Cross-lane guards
# ---------------------------------------------------------------------------


class TestGuards:
    def test_sell_lane_skips_exchange_locks_flag_on(self, exchange_env, monkeypatch):
        assert sellmon._exchange_lock_lane(42) is True
        assert sellmon._exchange_lock_lane("42") is True
        assert sellmon._exchange_lock_lane("sellq_abc") is False
        assert sellmon._exchange_lock_lane(True) is False
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "false")
        assert sellmon._exchange_lock_lane(42) is False

    def test_exchange_inflight_sweep_flag_gated(self, exchange_env, monkeypatch):
        sid = insert_exchange_settlement("trade", 99)
        update_exchange_settlement(sid, "settling", escrow_out_nonce=1, escrow_out_tx="{}")
        assert sellmon._exchange_inflight_sweep() is True
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "false")
        assert sellmon._exchange_inflight_sweep() is False

    def test_reserve_includes_exchange_rows(self, exchange_env):
        sid = insert_exchange_settlement("trade", 50, eth_amount=Decimal("0.002"))
        assert sid
        reserve = wdm._pending_eth_reserve()
        assert reserve == Decimal("0.002")

    def test_flag_off_disables(self, exchange_env, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "false")
        enabled, reason = esm.exchange_config_status()
        assert enabled is False and "disabled" in reason


# ---------------------------------------------------------------------------
# bridge_db additions — marks + prepay deposits
# ---------------------------------------------------------------------------


class TestLedgerAdditions:
    def test_monitor_mark_roundtrip(self, exchange_env):
        assert bridge_db.insert_monitor_mark("lock:0x1", detail="0xs", outcome="funded") is True
        assert bridge_db.insert_monitor_mark("lock:0x1") is False  # PK dedupe
        mark = bridge_db.monitor_mark("lock:0x1")
        assert mark["detail"] == "0xs" and mark["outcome"] == "funded"
        bridge_db.update_monitor_mark("lock:0x1", "ignored")
        assert bridge_db.monitor_mark("lock:0x1")["outcome"] == "ignored"

    def test_exchange_prepay_deposit_stays_out_of_payout_lane(self, exchange_env):
        did = insert_exchange_prepay_deposit("0xpre", "0xfrom", Decimal("0.01"), "0xN0DE")
        assert did.startswith("deposit_")
        conn = bridge_db._connect_db()
        row = conn.execute("SELECT status, recipient, amount_ait FROM eth_deposits WHERE tx_hash = '0xpre'").fetchone()
        conn.close()
        assert row[0] == "exchange_prepay"
        assert row[1] == "EXCHANGE_DEPOSIT:0xN0DE"
        assert Decimal(str(row[2])) == Decimal("0")
        assert bridge_db.get_pending_deposits() == []


# ---------------------------------------------------------------------------
# C5 fixup — owner check, zero/dust fee handling, flag independence
# ---------------------------------------------------------------------------


class TestFixup:
    @pytest.mark.asyncio
    async def test_foreign_lock_refunded_not_funded(self, exchange_env):
        """A lock sent by anyone but the order owner is a stray — refunded
        to its sender, never posted as order backing."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded")
        stranger = "0x6666666666666666666666666666666666666666"
        lock = _lock_tx(oid, "0xforeign", stranger, 3_636_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["funded"] == 0 and stats["refunds"] == 1
        assert not [p for p in exchange_env["posts"] if p["event"] == "order_funded"]
        row = get_exchange_settlement("order_refund", -oid)
        assert row is not None
        assert row["seller_address"] == stranger
        assert monitor_mark("lock:0xforeign")["outcome"] == "refunding"

    @pytest.mark.asyncio
    async def test_owner_lock_still_funds(self, exchange_env):
        """The owner check canonicalizes — same address in a different case
        spelling still funds its own order."""
        cfg = _cfg(exchange_env)
        owner = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        oid = _insert_order(exchange_env, order_type="SELL", funded_state="unfunded", user_address=owner)
        lock = _lock_tx(oid, "0xown", "0xABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCD", 3_636_000_000)
        lock["recipient"] = exchange_env["escrow"]
        exchange_env["transfers"].append(lock)
        stats = await esm._scan_order_locks(cfg, head=1000)
        assert stats["funded"] == 1

    @pytest.mark.asyncio
    async def test_zero_fee_settles_without_fee_leg(self, exchange_env):
        """EXCHANGE_FEE_PCT=0: leg 1 sealing settles the trade — no
        zero-value fee transfer to the treasury is ever signed."""
        cfg = _cfg(exchange_env)
        row = _trade_row(status="settling", escrow_out_nonce=3, escrow_out_tx="{}", fee_ait=Decimal("0"))
        leg1 = {
            "tx_hash": "0xleg1",
            "sender": exchange_env["escrow"],
            "recipient": BUYER_AIT,
            "value": 360_000_000,
            "block_height": 610,
            "nonce": 3,
            "payload": {"exs_ref": row["id"], "reason": "settling"},
        }
        exchange_env["transfers"].append(leg1)
        exchange_env["escrow_nonce"] = 4
        await esm._resolve_sweep(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "settled"
        assert fresh["settle_ait_tx_hash"] == "0xleg1"
        assert fresh["settle_fee_tx_hash"] is None
        assert exchange_env["ait_sends"] == []

    @pytest.mark.asyncio
    async def test_sub_unit_fee_settles_without_fee_leg(self, exchange_env):
        """A fee under one chain unit floors to zero — same skip as fee 0."""
        cfg = _cfg(exchange_env)
        row = _trade_row(
            status="settling",
            escrow_out_nonce=3,
            escrow_out_tx="{}",
            fee_ait=Decimal("0.00000001"),  # 1e-8 AIT < 1 unit (2.78e-8)
        )
        leg1 = {
            "tx_hash": "0xleg1",
            "sender": exchange_env["escrow"],
            "recipient": BUYER_AIT,
            "value": 360_000_000,
            "block_height": 610,
            "nonce": 3,
            "payload": {"exs_ref": row["id"], "reason": "settling"},
        }
        exchange_env["transfers"].append(leg1)
        exchange_env["escrow_nonce"] = 4
        await esm._resolve_sweep(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "settled"
        assert fresh["settle_ait_tx_hash"] == "0xleg1"
        assert exchange_env["ait_sends"] == []

    @pytest.mark.asyncio
    async def test_dust_remainder_skips_order_refund(self, exchange_env):
        """Cumulative-difference fees can leave a lock remainder below the
        sweep fee — refunding it would cost more than it returns."""
        cfg = _cfg(exchange_env)
        oid = _insert_order(
            exchange_env,
            order_type="SELL",
            status="filled",
            funded_state="funded",
            backing_tx_hash="0xback",
            locked_ticks=1_050_000_000,  # 10.5 AIT
        )
        _insert_trade(
            exchange_env,
            amount="10",
            fee_ait="0.495",
            sell_order_id=oid,
            settlement_state="settled",
        )
        # remainder = 10.5 − 10.495 = 0.005 AIT ≤ 0.01 sweep fee
        stats = await esm._scan_backing(cfg, head=1000)
        assert stats["refunds"] == 0
        assert get_exchange_settlement("order_refund", oid) is None

    @pytest.mark.asyncio
    async def test_above_dust_remainder_still_refunds(self, exchange_env):
        cfg = _cfg(exchange_env)
        oid = _insert_order(
            exchange_env,
            order_type="SELL",
            status="filled",
            funded_state="funded",
            backing_tx_hash="0xback2",
            locked_ticks=1_050_000_000,
        )
        _insert_trade(
            exchange_env,
            amount="10",
            fee_ait="0.45",
            sell_order_id=oid,
            settlement_state="settled",
        )
        # remainder = 0.05 AIT > 0.01 sweep fee → refund still created
        stats = await esm._scan_backing(cfg, head=1000)
        assert stats["refunds"] == 1
        assert get_exchange_settlement("order_refund", oid) is not None

    @pytest.mark.asyncio
    async def test_queued_fee_settle_with_zero_fee_settles(self, exchange_env):
        """A row parked by an older build with no fee owed settles instead
        of broadcasting a zero-value leg."""
        cfg = _cfg(exchange_env)
        row = _trade_row(
            status="queued_fee_settle",
            settle_ait_tx_hash="0xleg1",
            fee_ait=Decimal("0"),
        )
        await esm._resolve_sweep(cfg, row)
        fresh = get_exchange_settlement("trade", 1)
        assert fresh["status"] == "settled"
        assert exchange_env["ait_sends"] == []

    @pytest.mark.asyncio
    async def test_monitor_runs_with_sell_flag_unset(self, exchange_env, monkeypatch):
        """The exchange lane shares the escrow key slot but not the sell
        feature flag — a full poll works with SELL_ESCROW_ENABLED unset."""
        monkeypatch.delenv("SELL_ESCROW_ENABLED", raising=False)
        summary = await esm.poll_exchange_settlements_once()
        assert summary["skipped"] is False
        assert "locks" in summary and "credits" in summary
