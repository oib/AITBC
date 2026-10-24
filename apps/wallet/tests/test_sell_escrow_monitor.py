"""Tests for the escrowed AIT->ETH sell monitor (ETH-10 phase 1).

Covers:
- quote expiry + requote, orphan locks, double-submit dedupe
- reserve/cap enforcement from persisted rows across restarts
- stale-price parking, ETH-sent-then-DB-fail resume (ETH-9 case)
- refund failure -> failed with no second refund, deadline refund
- idempotent settle after restart, disabled-without-config, route validation
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from wallet_app.bridge import bridge_routes, bridge_withdraw_monitor as wdm
from wallet_app.bridge import sell_escrow_monitor as sellmon
from wallet_app.bridge.bridge_db import (
    _SELL_OPEN_STATUSES,
    get_sell_eth_committed_since,
    get_sell_lock_by_ait_tx_hash,
    get_sell_lock_by_quote_id,
    get_sell_quote,
    init_db,
    insert_sell_lock,
    insert_sell_quote,
    update_sell_lock_status,
)

# Throwaway test keys — generated constants, never real material.
TEST_ETH_PRIVATE_KEY = "0x" + "11" * 32
TEST_ETH_ADDRESS = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"
TEST_ESCROW_KEY = "0x" + "22" * 32
TEST_TREASURY = "0x3333333333333333333333333333333333333333"
SHOP_AIT = "0x4444444444444444444444444444444444444444"
SHOP_ETH = "0x5555555555555555555555555555555555555555"


def _escrow_address() -> str:
    from eth_keys import keys as eth_keys

    return eth_keys.PrivateKey(bytes.fromhex("22" * 32)).public_key.to_checksum_address()


def _fresh_feed(usd: Decimal = Decimal("3000")) -> dict[str, Any]:
    return {
        "usd": usd,
        "eur": Decimal("2800"),
        "feed_age_seconds": 10.0,
        "feed_source": "oracle",
    }


def _eth_rpc_stub(
    receipts: dict[str, Any] | None = None,
    nonces: dict[str, int] | None = None,
    block: int = 500,
    txs: dict[str, Any] | None = None,
    estimate: int = 21_000,
):
    """Dispatch wdm._eth_rpc calls used by the release-outcome checks.

    ``receipts``/``nonces`` may be mutable dicts owned by the test — rows
    can gain a chain outcome between polls. ``estimate`` feeds
    eth_estimateGas (ETH-14: release gas is estimated, not static).
    """
    receipts = receipts if receipts is not None else {}
    txs = txs or {}
    nonces = nonces if nonces is not None else {"latest": 0, "pending": 0}

    async def _stub(method: str, params: list[Any]) -> Any:
        if method == "eth_getTransactionReceipt":
            return receipts.get(params[0])
        if method == "eth_getTransactionByHash":
            return txs.get(params[0])
        if method == "eth_blockNumber":
            return hex(block)
        if method == "eth_getTransactionCount":
            return hex(nonces.get(params[1], 0))
        if method == "eth_estimateGas":
            return hex(estimate)
        raise AssertionError(f"unexpected eth_rpc call {method}")

    return _stub


@pytest.fixture
def sell_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Sell-monitor environment: tmp DB, escrow/signer/treasury configured,
    all chain + ETH RPC calls stubbed at the module seams."""
    db_path = tmp_path / "bridge.db"
    escrow = _escrow_address()

    # Throwaway escrow key slot: the ops-signer wallet format with a plain-hex
    # private_key — no credential needed (encrypted dicts are what need it).
    wallet_file = tmp_path / "escrow.json"
    wallet_file.write_text(json.dumps({"address": escrow, "private_key": TEST_ESCROW_KEY}))

    monkeypatch.setenv("AIT_SELL_ESCROW", escrow)
    monkeypatch.setenv("SELL_ESCROW_WALLET_PATH", str(wallet_file))
    monkeypatch.delenv("SELL_ESCROW_CREDENTIAL_FILE", raising=False)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setenv("SELL_TREASURY_ADDRESS", TEST_TREASURY)
    monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
    monkeypatch.setenv("AIT_USD_FIXED_PRICE", "0.28")
    monkeypatch.setenv("CHAIN_ID", "ait-testnet")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:0")
    monkeypatch.delenv("SELL_ESCROW_FUNDING_SOURCES", raising=False)
    monkeypatch.delenv("SELL_MAX_ETH_PER_TX", raising=False)
    monkeypatch.delenv("SELL_MAX_ETH_PER_DAY", raising=False)
    monkeypatch.delenv("SELL_RELEASE_DEADLINE", raising=False)
    monkeypatch.delenv("SELL_LOCK_ORPHAN_BLOCKS", raising=False)
    monkeypatch.delenv("ETH_WITHDRAW_MIN_RESERVE", raising=False)

    monkeypatch.setattr(wdm, "BRIDGE_ENABLED", True)
    monkeypatch.setattr(wdm, "ETH_WALLET_ADDRESS", TEST_ETH_ADDRESS)
    monkeypatch.setattr(wdm, "ETH_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
    monkeypatch.setattr(wdm, "BRIDGE_ADMIN_PRIVATE_KEY", "")
    # No static gas override — the release path must estimate (ETH-14).
    monkeypatch.setattr(wdm, "ETH_WITHDRAW_GAS", "")
    monkeypatch.setattr(wdm, "BLOCKCHAIN_RPC_URL", "http://localhost:0")

    async def _coro(value):
        return value

    state = {
        "eth_sends": [],
        "ait_sends": [],
        "escrow_nonce": 0,
        "escrow_balance": Decimal("1000"),
        "chain_height": 1000,
        "receipts": {},
        "nonces": {"latest": 0, "pending": 0},
    }

    monkeypatch.setattr(wdm, "_eth_balance", lambda address: _coro(Decimal("0.1")))
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
        state.setdefault("scan_limits", []).append(limit)
        return list(state.get("transfers", []))

    async def _height() -> int:
        return int(state["chain_height"])

    monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast)
    monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _ait_broadcast)
    monkeypatch.setattr(sellmon, "_account_view", _account_view)
    monkeypatch.setattr(sellmon, "_fetch_transfers", _transfers)
    monkeypatch.setattr(sellmon, "_chain_height", _height)
    monkeypatch.setattr(sellmon, "get_eth_prices_fresh", lambda: _coro(_fresh_feed()))
    monkeypatch.setattr(sellmon, "_db_initialized", False)

    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        state["escrow"] = escrow
        yield state


def _insert_quote(expired: bool = False, ait_amount: Decimal = Decimal("10")) -> str:
    """Insert a live (or expired) quote at a consistent rate and return its id.

    fee = 0.5% of gross; eth_amount = net * 0.28 / 3000 — matching what
    apply_bridge_fee + the feed constants produce.
    """
    fee_ait = (ait_amount * Decimal("0.005")).quantize(Decimal("0.000001"))
    net_ait = ait_amount - fee_ait
    eth_amount = (net_ait * Decimal("0.28") / Decimal("3000")).quantize(Decimal("0.00000001"))
    expires = datetime.now() + (timedelta(seconds=-60) if expired else timedelta(seconds=900))
    return insert_sell_quote(
        shop_ait_address=SHOP_AIT,
        shop_eth_address=SHOP_ETH,
        ait_amount=ait_amount,
        rate_eth_usd=Decimal("3000"),
        ait_usd=Decimal("0.28"),
        fee_ait=fee_ait,
        eth_amount=eth_amount,
        expires_at=expires.isoformat(),
    )


def _lock_tx(
    quote_id: str | None,
    tx_hash: str | None = None,
    height: int = 900,
    ait: Decimal = Decimal("10"),
    sender: str = SHOP_AIT,
) -> dict:
    from aitbc.utils import ait_to_units

    return {
        "tx_hash": tx_hash or "0x" + "aa" * 32,
        "sender": sender,
        "recipient": _escrow_address(),
        "value": ait_to_units(ait),
        "payload": {"sell_quote": quote_id} if quote_id else {},
        "block_height": height,
        "nonce": 1,
        "status": "confirmed",
        "type": "TRANSFER",
    }


async def _prove_release_sent(sell_env: dict, ait_tx_hash: str) -> None:
    """Give a 'releasing' row's recorded release a deep successful receipt
    and run one poll — the ETH-14 gate: only a verified receipt may move
    the row 'released'."""
    row = get_sell_lock_by_ait_tx_hash(ait_tx_hash)
    assert row is not None and row["status"] == "releasing"
    sell_env["receipts"][row["eth_tx_hash"]] = {"status": "0x1", "blockNumber": hex(450)}
    sell_env["transfers"] = []
    await sellmon.poll_sells_once()


def _backdate_lock_release(ait_tx_hash: str, seconds: int) -> None:
    """Move a sell lock's released_at (release-intent write time) into the
    past so the absence grace no longer covers it."""
    from wallet_app.bridge import bridge_db as db

    old = (datetime.now() - timedelta(seconds=seconds)).isoformat()
    conn = db._connect_db()
    conn.execute("UPDATE bridge_sell_locks SET released_at = ? WHERE ait_tx_hash = ?", (old, ait_tx_hash))
    conn.commit()
    conn.close()


def _sealed_sweep_tx(
    sell_ref: str,
    to: str,
    ait: Decimal,
    nonce: int,
    tx_hash: str | None = None,
    height: int = 950,
) -> dict:
    """A *sealed* escrow outbound TRANSFER as the chain scan would return it —
    carries every field _find_escrow_outflow matches on."""
    from aitbc.utils import ait_to_units

    return {
        "tx_hash": tx_hash or "0x" + "77" * 32,
        "sender": _escrow_address(),
        "recipient": to,
        "value": ait_to_units(ait),
        "payload": {"amount": ait_to_units(ait), "sell_ref": sell_ref, "reason": "x"},
        "block_height": height,
        "nonce": nonce,
        "status": "confirmed",
        "type": "TRANSFER",
    }


class TestSellDisabled:
    def test_disabled_without_escrow_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
        monkeypatch.delenv("SELL_TREASURY_ADDRESS", raising=False)
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
        monkeypatch.setattr(wdm, "BRIDGE_ENABLED", True)

        enabled, reason = sellmon.sell_config_status()
        assert not enabled
        assert "AIT_SELL_ESCROW" in reason

    @pytest.mark.asyncio
    async def test_poll_skips_when_unconfigured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
        monkeypatch.delenv("SELL_TREASURY_ADDRESS", raising=False)
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
        monkeypatch.setattr(wdm, "BRIDGE_ENABLED", True)

        result = await sellmon.poll_sells_once()
        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_flag_off_disables_everything(self, sell_env, monkeypatch):
        """SELL_ESCROW_ENABLED=false gates the whole feature even when the
        key slot and every address are configured."""
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "false")
        enabled, reason = sellmon.sell_config_status()
        assert not enabled
        assert "sell escrow disabled" in reason

        result = await sellmon.poll_sells_once()
        assert result["skipped"] is True
        assert result["processed"] == 0

    @pytest.mark.asyncio
    async def test_missing_key_slot_disables(self, sell_env, monkeypatch):
        """Key slot missing/unreadable -> poll skips, never a fallback key."""
        monkeypatch.setenv("SELL_ESCROW_WALLET_PATH", "/nonexistent/escrow.json")
        result = await sellmon.poll_sells_once()
        assert result["skipped"] is True
        assert "escrow key slot" in result["reason"].lower()

    def test_invalid_cap_refuses_start(self, sell_env, monkeypatch):
        monkeypatch.setenv("SELL_MAX_ETH_PER_TX", "bogus")
        enabled, reason = sellmon.sell_config_status()
        assert not enabled
        assert "SELL_MAX_ETH_PER_TX" in reason


class TestSellRouteGateHardening:
    """SEC-18: the 503 body is a fixed string; the config detail goes to the log."""

    def test_gate_503_body_is_fixed_and_reason_logged(self, monkeypatch, caplog):
        monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
        monkeypatch.delenv("SELL_TREASURY_ADDRESS", raising=False)
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
        monkeypatch.setattr(wdm, "BRIDGE_ENABLED", True)

        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.bridge_routes"):
            with pytest.raises(HTTPException) as excinfo:
                bridge_routes._sell_gate()
        assert excinfo.value.status_code == 503
        assert excinfo.value.detail == "Sell escrow disabled"
        assert "AIT_SELL_ESCROW" not in excinfo.value.detail
        assert "AIT_SELL_ESCROW" in caplog.text

    @pytest.mark.asyncio
    async def test_quote_config_error_503_body_is_fixed_and_logged(self, monkeypatch, caplog):
        def _boom():
            raise ValueError("AIT_SELL_ESCROW (escrow address) not configured")

        monkeypatch.setattr(sellmon, "sell_config_status", lambda: (True, ""))
        monkeypatch.setattr(sellmon, "_sell_config", _boom)
        monkeypatch.setattr(
            bridge_routes,
            "_validate_sell_quote_params",
            lambda body: (Decimal("1"), TEST_ETH_ADDRESS, SHOP_AIT),
        )
        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.bridge_routes"):
            with pytest.raises(HTTPException) as excinfo:
                await bridge_routes.bridge_sell_quote({}, None)
        assert excinfo.value.status_code == 503
        assert excinfo.value.detail == "Sell escrow disabled"
        assert "AIT_SELL_ESCROW" not in excinfo.value.detail
        assert "AIT_SELL_ESCROW" in caplog.text

    @pytest.mark.asyncio
    async def test_poll_skip_503_body_is_fixed_and_reason_logged(self, monkeypatch, caplog):
        async def _skipped_poll():
            return {"skipped": True, "reason": "ETH_WALLET_ADDRESS not set"}

        monkeypatch.setattr(bridge_routes, "poll_once", _skipped_poll)
        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.bridge_routes"):
            with pytest.raises(HTTPException) as excinfo:
                await bridge_routes.trigger_bridge_poll(None)
        assert excinfo.value.status_code == 503
        assert excinfo.value.detail == "Bridge poll skipped"
        assert "ETH_WALLET_ADDRESS" not in excinfo.value.detail
        assert "ETH_WALLET_ADDRESS" in caplog.text


class TestQuoteAndLockMatching:
    @pytest.mark.asyncio
    async def test_lock_with_live_quote_releases(self, sell_env):
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        result = await sellmon.poll_sells_once()
        assert result["recorded"] == 1
        assert len(sell_env["eth_sends"]) == 1

        # ETH-14: broadcast alone leaves the row 'releasing'.
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"
        assert row["quote_id"] == quote_id
        assert row["eth_tx_hash"]
        assert row["release_nonce"] == 7
        assert get_sell_quote(quote_id)["status"] == "locked"

        # A verified status-1 receipt at depth moves it 'released'.
        await _prove_release_sent(sell_env, "0x" + "aa" * 32)
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "released"

    @pytest.mark.asyncio
    async def test_lock_on_expired_quote_requotes(self, sell_env):
        quote_id = _insert_quote(expired=True)
        sell_env["transfers"] = [_lock_tx(quote_id)]

        result = await sellmon.poll_sells_once()
        assert result["recorded"] == 1
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["requoted"] == 1
        assert row["eth_amount"] is not None
        assert row["status"] == "releasing"
        assert get_sell_quote(quote_id)["status"] == "expired"

        await _prove_release_sent(sell_env, "0x" + "aa" * 32)
        assert get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)["status"] == "released"

    @pytest.mark.asyncio
    async def test_expired_quote_stale_feed_parks(self, sell_env, monkeypatch):
        quote_id = _insert_quote(expired=True)
        sell_env["transfers"] = [_lock_tx(quote_id)]

        async def _stale():
            return None

        monkeypatch.setattr(sellmon, "get_eth_prices_fresh", _stale)
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "stale_price"
        assert len(sell_env["eth_sends"]) == 0

    @pytest.mark.asyncio
    async def test_lock_without_quote_is_orphan_then_refunded(self, sell_env):
        sell_env["transfers"] = [_lock_tx(None, tx_hash="0x" + "bb" * 32, height=100)]
        sell_env["chain_height"] = 100  # inside the orphan window

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "bb" * 32)
        assert row["status"] == "orphaned"
        assert not sell_env["ait_sends"]

        sell_env["transfers"] = []
        sell_env["chain_height"] = 300  # 200 blocks > SELL_LOCK_ORPHAN_BLOCKS=150
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "bb" * 32)
        # Refund broadcast happened, but the row is in-flight until the
        # outflow is found *sealed* — broadcast alone never finalizes.
        assert row["status"] == "refunding"
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT

        # Seal the outflow; the next poll credits it by strict match.
        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref="0x" + "bb" * 32, to=SHOP_AIT, ait=Decimal("10"), nonce=0)]
        sell_env["escrow_nonce"] = 1
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "bb" * 32)
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"] == "0x" + "77" * 32

    @pytest.mark.asyncio
    async def test_lock_sender_mismatch_orphans_and_refunds_sender(self, sell_env):
        """A lock paying into a live quote id but sent by a DIFFERENT address
        than the quote's shop_ait_address is orphan-refunded — to the actual
        sender, never releasing against somebody else's quote."""
        other = "0x6666666666666666666666666666666666666666"
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id, tx_hash="0x" + "bc" * 32, height=100, sender=other)]
        sell_env["chain_height"] = 100

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "bc" * 32)
        assert row["status"] == "orphaned"
        assert "does not match" in (row["error"] or "")
        assert row["shop_ait_address"] == other  # refund target is the real sender
        assert not sell_env["eth_sends"]
        # The quote was NOT consumed by the foreign lock.
        assert get_sell_quote(quote_id)["status"] == "quoted"

        sell_env["transfers"] = []
        sell_env["chain_height"] = 300
        await sellmon.poll_sells_once()
        assert get_sell_lock_by_ait_tx_hash("0x" + "bc" * 32)["status"] == "refunding"
        assert sell_env["ait_sends"][0]["to"].lower() == other.lower()

    @pytest.mark.asyncio
    async def test_funding_source_send_never_locked(self, sell_env, monkeypatch):
        """SELL_ESCROW_FUNDING_SOURCES sends are float top-ups — skipped by
        the scan so the operator's seed cannot be orphan-refunded back."""
        monkeypatch.setenv("SELL_ESCROW_FUNDING_SOURCES", "0x7777777777777777777777777777777777777777")
        sell_env["transfers"] = [
            _lock_tx(None, tx_hash="0x" + "bd" * 32, height=100, sender="0x7777777777777777777777777777777777777777")
        ]
        result = await sellmon.poll_sells_once()
        assert result["recorded"] == 0
        assert get_sell_lock_by_ait_tx_hash("0x" + "bd" * 32) is None

    @pytest.mark.asyncio
    async def test_double_submit_same_lock_releases_once(self, sell_env):
        quote_id = _insert_quote()
        tx = _lock_tx(quote_id)
        sell_env["transfers"] = [tx, dict(tx)]  # same tx seen twice in one scan

        await sellmon.poll_sells_once()
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row is not None
        assert len(sell_env["eth_sends"]) == 1

    @pytest.mark.asyncio
    async def test_second_lock_on_consumed_quote_is_orphaned(self, sell_env):
        quote_id = _insert_quote()
        sell_env["transfers"] = [
            _lock_tx(quote_id, tx_hash="0x" + "aa" * 32),
            _lock_tx(quote_id, tx_hash="0x" + "cc" * 32),
        ]
        await sellmon.poll_sells_once()
        first = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        second = get_sell_lock_by_ait_tx_hash("0x" + "cc" * 32)
        assert first["status"] == "releasing"
        assert second["status"] == "orphaned"
        assert len(sell_env["eth_sends"]) == 1

        await _prove_release_sent(sell_env, "0x" + "aa" * 32)
        assert get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)["status"] == "released"


class TestCapsAndReserve:
    @pytest.mark.asyncio
    async def test_queued_reserve_queues_then_releases(self, sell_env, monkeypatch):
        async def _low(_addr):
            return Decimal("0.006")

        monkeypatch.setattr(wdm, "_eth_balance", _low)
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "queued_reserve"
        assert not sell_env["eth_sends"]

        async def _ok(_addr):
            return Decimal("0.1")

        monkeypatch.setattr(wdm, "_eth_balance", _ok)
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"
        assert len(sell_env["eth_sends"]) == 1

        await _prove_release_sent(sell_env, "0x" + "aa" * 32)
        assert get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)["status"] == "released"

    @pytest.mark.asyncio
    async def test_per_tx_cap_queues(self, sell_env):
        # 120 AIT nets ~0.0111 ETH at 0.28/3000 — over the 0.01 per-tx cap.
        quote_id = _insert_quote(ait_amount=Decimal("120"))
        tx = _lock_tx(quote_id, ait=Decimal("120"))
        sell_env["transfers"] = [tx]

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "queued_reserve"
        assert "SELL_MAX_ETH_PER_TX" in (row["error"] or "")
        assert not sell_env["eth_sends"]

    @pytest.mark.asyncio
    async def test_daily_cap_from_persisted_rows_across_restart(self, sell_env):
        # Simulate "restarted" state: a settled sell from earlier today.
        insert_sell_lock(
            ait_tx_hash="0x" + "dd" * 32,
            shop_ait_address=SHOP_AIT,
            amount_ait=Decimal("300"),
            status="locked",
        )
        update_sell_lock_status("0x" + "dd" * 32, "released", eth_amount=Decimal("0.0295"))
        update_sell_lock_status("0x" + "dd" * 32, "settled")

        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]  # ~0.0009 ETH → 0.0295+0.0009 > 0.03
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "queued_reserve"
        assert "daily" in (row["error"] or "")
        assert not sell_env["eth_sends"]


class TestStalePriceParking:
    @pytest.mark.asyncio
    async def test_feed_goes_stale_before_release(self, sell_env, monkeypatch):
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        sell_env["stale_next"] = True

        calls = {"n": 0}

        async def _flaky_feed():
            calls["n"] += 1
            # compute path not hit (quote still fresh); release-time check stale
            return None

        monkeypatch.setattr(sellmon, "get_eth_prices_fresh", _flaky_feed)
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "stale_price"
        assert not sell_env["eth_sends"]

        # Feed recovers -> next poll releases.
        async def _fresh():
            return _fresh_feed()

        monkeypatch.setattr(sellmon, "get_eth_prices_fresh", _fresh)
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"
        assert len(sell_env["eth_sends"]) == 1

        await _prove_release_sent(sell_env, "0x" + "aa" * 32)
        assert get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)["status"] == "released"


class TestReleaseOutcomeAndResume:
    @pytest.mark.asyncio
    async def test_eth_sent_then_db_failure_no_refund_resume_completes(self, sell_env, monkeypatch):
        """The ETH-9 case: broadcast lands, the 'released' write keeps failing —
        no refund may issue; after the DB recovers, the resume path completes
        and settles the row."""
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        real_update = sellmon.update_sell_lock_status

        def _flaky_update(ait_tx_hash, status, **kwargs):
            if status == "released":
                raise sqlite3.OperationalError("disk i/o")
            return real_update(ait_tx_hash, status, **kwargs)

        # The recorded release is provably on-chain: deep successful receipt.
        async def _eth_rpc(method: str, params: list[Any]) -> Any:
            if method == "eth_getTransactionReceipt":
                return {"status": "0x1", "blockNumber": hex(450)}
            if method == "eth_getTransactionByHash":
                return {"hash": params[0]}
            if method == "eth_blockNumber":
                return hex(460)
            if method == "eth_getTransactionCount":
                return hex(8)
            if method == "eth_estimateGas":
                return hex(21_000)
            raise AssertionError(method)

        monkeypatch.setattr(wdm, "_eth_rpc", _eth_rpc)
        monkeypatch.setattr(sellmon, "update_sell_lock_status", _flaky_update)
        await sellmon.poll_sells_once()

        # ETH-14: the broadcast itself only leaves 'releasing'; the
        # 'released' write happens on the verified inflight pass — poll
        # again with the DB still failing: exhausted retries keep the row
        # open and no refund issues.
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"
        assert row["eth_tx_hash"]
        assert not sell_env["ait_sends"]  # no refund despite the failure

        # DB recovered — real updater again; the verified receipt completes it.
        monkeypatch.setattr(sellmon, "update_sell_lock_status", real_update)
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "released"

        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "settling"
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == TEST_TREASURY

        # The sealed outflow closes the row — one AIT leg, no refund.
        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref="0x" + "aa" * 32, to=TEST_TREASURY, ait=Decimal("10"), nonce=0)]
        sell_env["escrow_nonce"] = 1
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "settled"
        assert row["settle_tx_hash"] == "0x" + "77" * 32
        assert len(sell_env["ait_sends"]) == 1
        assert len(sell_env["eth_sends"]) == 1

    @pytest.mark.asyncio
    async def test_releasing_row_never_sent_refunds(self, sell_env, monkeypatch):
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        async def _broadcast_fail(raw):
            raise RuntimeError("node rejected")

        monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast_fail)
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        # Absence on a just-written intent is 'unknown' inside the grace —
        # needs_review; the proven-unsent refund runs once the row is old.
        assert row["status"] == "needs_review"
        _backdate_lock_release("0x" + "aa" * 32, wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        # Release provably unsent -> refund_pending, refund sweep in flight.
        assert row["status"] == "refunding"
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT

        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref="0x" + "aa" * 32, to=SHOP_AIT, ait=Decimal("10"), nonce=0)]
        sell_env["escrow_nonce"] = 1
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"] == "0x" + "77" * 32

    @pytest.mark.asyncio
    async def test_refund_broadcast_throw_stays_inflight_rebroadcasts_identical(self, sell_env, monkeypatch):
        """A refund broadcast that throws post-intent leaves the row
        'refunding'; the resolver re-broadcasts the *stored* blob — same
        nonce, same signature — so a retry can never double-pay."""
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        async def _broadcast_fail(raw):
            raise RuntimeError("node rejected")

        sends = {"fail_next": True}

        async def _ait_maybe_fail(tx):
            if sends["fail_next"]:
                sends["fail_next"] = False
                raise RuntimeError("rpc down")
            sell_env["ait_sends"].append(tx)
            return "0x" + "ff" * 32

        monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast_fail)
        monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _ait_maybe_fail)
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        # Young + absent is 'unknown' under the grace — the row parks at
        # needs_review; aging it past the window reaches the refund path.
        assert row["status"] == "needs_review"
        _backdate_lock_release("0x" + "aa" * 32, wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "refunding"
        blob = json.loads(row["escrow_out_tx"])
        assert not sell_env["ait_sends"]  # the only attempt threw pre-seal

        # Next poll: resolver re-broadcasts the stored blob verbatim.
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0] == blob  # identical — chain dedups
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "refunding"  # still in flight until sealed

        # Seal it — strict match credits the refund.
        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref="0x" + "aa" * 32, to=SHOP_AIT, ait=Decimal("10"), nonce=0)]
        sell_env["escrow_nonce"] = 1
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "refunded"
        assert len(sell_env["ait_sends"]) == 1  # only ever one payment blob

    @pytest.mark.asyncio
    async def test_unknown_outcome_needs_review_no_refund(self, sell_env, monkeypatch):
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        async def _broadcast_fail(raw):
            raise RuntimeError("timeout")

        monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast_fail)
        # consumed nonce, no receipt -> unknown (ETH-9b case)
        monkeypatch.setattr(wdm, "_eth_rpc", _eth_rpc_stub(nonces={"latest": 8, "pending": 8}))
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        assert not sell_env["ait_sends"]

    @pytest.mark.asyncio
    async def test_absent_release_grace_unknown_then_refund(self, sell_env, monkeypatch):
        """ETH-14b: a just-broadcast release that the (lagging) RPC cannot
        see is 'unknown' inside ETH_RELEASE_ABSENCE_GRACE_SECONDS — the
        inflight check parks it needs_review and must not refund; once
        older than the window the same view is proven not_sent."""
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"
        assert len(sell_env["eth_sends"]) == 1

        # RPC sees nothing: no tx, no receipt, nonce not visibly used.
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        assert not sell_env["ait_sends"]  # no refund issued

        # Past the grace window the same absence proves not_sent.
        _backdate_lock_release("0x" + "aa" * 32, wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] in ("refund_pending", "refunding")
        assert len(sell_env["ait_sends"]) == 1


class TestGraceLogLevel:
    """ETH-15: an in-grace absence parks needs_review but logs at WARNING
    (routine propagation lag); 'unknown' for any other reason stays ERROR."""

    def _sell_records(self, caplog):
        return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "wallet_app.bridge.sell_escrow_monitor"]

    @pytest.mark.asyncio
    async def test_in_grace_absence_logs_warning_not_error(self, sell_env, monkeypatch, caplog):
        import logging

        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        await sellmon.poll_sells_once()  # releases — row goes 'releasing'
        assert get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)["status"] == "releasing"

        sell_env["transfers"] = []
        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.sell_escrow_monitor"):
            await sellmon.poll_sells_once()  # RPC sees nothing — in-grace
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        msgs = self._sell_records(caplog)
        assert any(lvl == logging.WARNING and "absence grace" in m for lvl, m in msgs)
        assert not any(lvl >= logging.ERROR for lvl, m in msgs)

    @pytest.mark.asyncio
    async def test_non_absence_unknown_still_errors(self, sell_env, monkeypatch, caplog):
        """A consumed nonce without a receipt is a real 'unknown' — ERROR."""
        import logging

        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        await sellmon.poll_sells_once()
        sell_env["transfers"] = []
        # Release nonce consumed, recorded hash never landed.
        sell_env["nonces"]["latest"] = 8
        sell_env["nonces"]["pending"] = 8

        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.sell_escrow_monitor"):
            await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        msgs = self._sell_records(caplog)
        assert any(lvl >= logging.ERROR and "unverifiable" in m for lvl, m in msgs)
        assert not any(lvl == logging.WARNING and "absence grace" in m for lvl, m in msgs)

    @pytest.mark.asyncio
    async def test_young_pending_release_logs_warning(self, sell_env, monkeypatch, caplog):
        """ETH-18 (the ETH-16 case): a just-broadcast release whose tx is
        visible but unmined/below depth is a routine delay — WARNING (the
        row did park needs_review), never ERROR, with reason and age."""
        import logging

        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"

        sell_env["transfers"] = []
        tx_hash = row["eth_tx_hash"]
        monkeypatch.setattr(
            wdm,
            "_eth_rpc",
            _eth_rpc_stub(txs={tx_hash: {"hash": tx_hash}}, receipts={}, nonces={"latest": 0, "pending": 0}),
        )
        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.sell_escrow_monitor"):
            await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        msgs = self._sell_records(caplog)
        assert any(lvl == logging.WARNING and "reason=chain_view" in m and "age=" in m for lvl, m in msgs)
        assert not any(lvl >= logging.ERROR for lvl, m in msgs)

    @pytest.mark.asyncio
    async def test_old_pending_release_logs_error(self, sell_env, monkeypatch, caplog):
        """ETH-18: the same pending chain view past the grace window is
        genuinely unverifiable — stays ERROR with the reason named."""
        import logging

        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        tx_hash = row["eth_tx_hash"]

        sell_env["transfers"] = []
        _backdate_lock_release("0x" + "aa" * 32, wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        monkeypatch.setattr(
            wdm,
            "_eth_rpc",
            _eth_rpc_stub(txs={tx_hash: {"hash": tx_hash}}, receipts={}, nonces={"latest": 0, "pending": 0}),
        )
        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.sell_escrow_monitor"):
            await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        msgs = self._sell_records(caplog)
        assert any(lvl >= logging.ERROR and "unverifiable" in m and "reason=chain_view" in m for lvl, m in msgs)

    @pytest.mark.asyncio
    async def test_verify_error_logs_error(self, sell_env, monkeypatch, caplog):
        """An RPC failure is never routine — verify_error keeps ERROR even
        on a just-broadcast lock."""
        import logging

        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]
        await sellmon.poll_sells_once()
        assert get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)["status"] == "releasing"

        sell_env["transfers"] = []

        async def _failing_rpc(method, params):
            raise RuntimeError("RPC unreachable")

        monkeypatch.setattr(wdm, "_eth_rpc", _failing_rpc)
        with caplog.at_level(logging.WARNING, logger="wallet_app.bridge.sell_escrow_monitor"):
            await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "needs_review"
        msgs = self._sell_records(caplog)
        assert any(lvl >= logging.ERROR and "unverifiable" in m and "reason=verify_error" in m for lvl, m in msgs)


class TestDeadlines:
    @pytest.mark.asyncio
    async def test_deadline_refund(self, sell_env, monkeypatch):
        """A 'locked' row past SELL_RELEASE_DEADLINE is refunded, not released."""
        quote_id = _insert_quote()
        insert_sell_lock(
            ait_tx_hash="0x" + "de" * 32,
            quote_id=quote_id,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            status="locked",
            locked_height=900,
        )
        # Simulate a lock seen 2h ago (SELL_RELEASE_DEADLINE default 3600s).
        monkeypatch.setattr(sellmon, "_lock_age_seconds", lambda row: 7200.0)

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "de" * 32)
        assert row["status"] == "refunding"
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT
        assert not sell_env["eth_sends"]

        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref="0x" + "de" * 32, to=SHOP_AIT, ait=Decimal("10"), nonce=0)]
        sell_env["escrow_nonce"] = 1
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "de" * 32)
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"] == "0x" + "77" * 32

    @pytest.mark.asyncio
    async def test_rpc_outage_cannot_refund_past_deadline(self, sell_env, monkeypatch):
        """A failed scan aborts the poll — a deadline-expired lock is not
        refunded on the strength of stale/broken chain data."""
        insert_sell_lock(
            ait_tx_hash="0x" + "df" * 32,
            shop_ait_address=SHOP_AIT,
            amount_ait=Decimal("10"),
            status="locked",
            locked_height=900,
        )
        monkeypatch.setattr(sellmon, "_lock_age_seconds", lambda row: 7200.0)

        async def _scan_fail(address: str, limit: int = 500) -> list[dict]:
            raise ConnectionError("chain RPC down")

        monkeypatch.setattr(sellmon, "_fetch_transfers", _scan_fail)
        result = await sellmon.poll_sells_once()
        assert result["skipped"] is True
        row = get_sell_lock_by_ait_tx_hash("0x" + "df" * 32)
        assert row["status"] == "locked"  # untouched — retried next healthy poll
        assert not sell_env["ait_sends"]


class TestSettleResume:
    @pytest.mark.asyncio
    async def test_settling_row_recovered_by_nonce_after_restart(self, sell_env):
        """A 'settling' row whose broadcast sealed before the crash is
        recovered by strict outflow match — settled once, never re-sent."""
        insert_sell_lock(
            ait_tx_hash="0x" + "ee" * 32,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            eth_amount=Decimal("0.0009"),
            status="released",
            locked_height=900,
        )
        update_sell_lock_status("0x" + "ee" * 32, "settling", escrow_out_nonce=5)

        sell_env["transfers"] = [
            _sealed_sweep_tx(
                sell_ref="0x" + "ee" * 32,
                to=TEST_TREASURY,
                ait=Decimal("10"),
                nonce=5,
                tx_hash="0x" + "99" * 32,
            )
        ]
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "ee" * 32)
        assert row["status"] == "settled"
        assert row["settle_tx_hash"] == "0x" + "99" * 32
        assert not sell_env["ait_sends"]  # recovered by nonce, not re-sent

    @pytest.mark.asyncio
    async def test_foreign_tx_at_recorded_nonce_never_credited(self, sell_env):
        """A *different* sealed tx at the recorded nonce (manual send) does
        not match nonce+recipient+amount+sell_ref — the row goes to
        needs_review, never 'settled' on somebody else's transaction."""
        insert_sell_lock(
            ait_tx_hash="0x" + "f0" * 32,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            eth_amount=Decimal("0.0009"),
            status="released",
            locked_height=900,
        )
        update_sell_lock_status("0x" + "f0" * 32, "settling", escrow_out_nonce=5)

        # A foreign sealed tx consumed nonce 5: right sender+nonce, wrong
        # recipient/amount/sell_ref. Account nonce has moved past it.
        sell_env["transfers"] = [
            _sealed_sweep_tx(
                sell_ref="0x" + "fe" * 32,  # different sell_ref
                to=TEST_TREASURY,
                ait=Decimal("10"),
                nonce=5,
                tx_hash="0x" + "88" * 32,
            )
        ]
        sell_env["escrow_nonce"] = 6
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "f0" * 32)
        assert row["status"] == "needs_review_sweep"
        assert "unmatched" in (row["error"] or "")
        assert not row["settle_tx_hash"]
        assert not sell_env["ait_sends"]  # no blind re-send

        # Terminal for the machine: further polls must not route the row
        # into the release check (which would read 'sent' and re-sweep).
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "f0" * 32)
        assert row["status"] == "needs_review_sweep"
        assert row["escrow_out_nonce"] == 5  # intent not re-bound to a fresh sweep
        assert not sell_env["ait_sends"]
        assert not sell_env["eth_sends"]
        """Crash-resume: stored blob re-broadcasts verbatim each poll while
        the nonce stays free, then the seal finalizes — never a new nonce."""
        insert_sell_lock(
            ait_tx_hash="0x" + "ef" * 32,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            eth_amount=Decimal("0.0009"),
            status="released",
            locked_height=900,
        )
        stored_blob = json.dumps({"type": "TRANSFER", "nonce": 5, "to": TEST_TREASURY})
        update_sell_lock_status("0x" + "ef" * 32, "settling", escrow_out_nonce=5, escrow_out_tx=stored_blob)
        sell_env["transfers"] = []  # nonce 5 never sealed
        sell_env["escrow_nonce"] = 5

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "ef" * 32)
        assert row["status"] == "settling"  # in flight until sealed
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["nonce"] == 5

        # A second poll while still unsealed re-broadcasts the SAME blob.
        await sellmon.poll_sells_once()
        assert len(sell_env["ait_sends"]) == 2
        assert sell_env["ait_sends"][1]["nonce"] == 5

        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref="0x" + "ef" * 32, to=TEST_TREASURY, ait=Decimal("10"), nonce=5)]
        sell_env["escrow_nonce"] = 6
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "ef" * 32)
        assert row["status"] == "settled"
        assert row["settle_tx_hash"] == "0x" + "77" * 32


class TestSweepReviewIsTerminal:
    """A sweep-path 'needs_review_sweep' row is never auto-processed — the
    release check must not turn it back into released/refund_pending, and no
    new sweep may be signed for it. Only an operator action moves it."""

    @pytest.mark.asyncio
    async def test_missing_sweep_nonce_is_terminal(self, sell_env):
        quote_id = _insert_quote()
        insert_sell_lock(
            ait_tx_hash="0x" + "c1" * 32,
            quote_id=quote_id,
            shop_ait_address=SHOP_AIT,
            amount_ait=Decimal("10"),
            status="settling",
            locked_height=900,
        )
        # settling row with no persisted escrow nonce — undecidable.
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "c1" * 32)
        assert row["status"] == "needs_review_sweep"
        assert "nonce missing" in (row["error"] or "")

        await sellmon.poll_sells_once()
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "c1" * 32)
        assert row["status"] == "needs_review_sweep"
        assert not sell_env["ait_sends"]
        assert not sell_env["eth_sends"]
        # The lock still binds its quote — a sibling cannot claim it.
        bound = get_sell_lock_by_quote_id(quote_id, statuses=sellmon._SELL_BINDING_STATUSES)
        assert bound is not None and bound["ait_tx_hash"] == "0x" + "c1" * 32

    @pytest.mark.asyncio
    async def test_missing_sweep_blob_is_terminal(self, sell_env):
        quote_id = _insert_quote()
        insert_sell_lock(
            ait_tx_hash="0x" + "c2" * 32,
            quote_id=quote_id,
            shop_ait_address=SHOP_AIT,
            amount_ait=Decimal("10"),
            status="refunding",
            locked_height=900,
        )
        update_sell_lock_status("0x" + "c2" * 32, "refunding", escrow_out_nonce=5)
        sell_env["transfers"] = []  # nothing sealed at nonce 5
        sell_env["escrow_nonce"] = 5  # nonce still free, but no stored blob

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "c2" * 32)
        assert row["status"] == "needs_review_sweep"
        assert "blob missing" in (row["error"] or "")

        await sellmon.poll_sells_once()
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "c2" * 32)
        assert row["status"] == "needs_review_sweep"
        assert not sell_env["ait_sends"]
        assert not sell_env["eth_sends"]

    @pytest.mark.asyncio
    async def test_release_path_needs_review_still_resumes(self, sell_env, monkeypatch):
        """Reverse case: a *release*-path needs_review row keeps the old
        behaviour — a receipt that later turns up 'sent' resumes to
        'released' and its settle sweep proceeds."""
        h, e = "0x" + "c3" * 32, "0x" + "3c" * 32
        insert_sell_lock(
            ait_tx_hash=h,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            eth_amount=Decimal("0.0009"),
            status="needs_review",
            locked_height=900,
        )
        update_sell_lock_status(h, "needs_review", eth_tx_hash=e, release_nonce=9)
        monkeypatch.setattr(
            wdm,
            "_eth_rpc",
            _eth_rpc_stub(
                receipts={e: {"status": "0x1", "blockNumber": hex(450)}},
                nonces={"latest": 10, "pending": 10},
                block=460,
            ),
        )

        await sellmon.poll_sells_once()
        assert get_sell_lock_by_ait_tx_hash(h)["status"] == "released"

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash(h)
        assert row["status"] == "settling"
        assert len(sell_env["ait_sends"]) == 1  # the settle sweep started


class TestSweepSerialization:
    """At most one escrow sweep is in flight; a new one waits for seal."""

    def _released_row(self, tx_hash: str, eth_hash: str, nonce: int) -> None:
        insert_sell_lock(
            ait_tx_hash=tx_hash,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            eth_amount=Decimal("0.0009"),
            status="released",
            locked_height=900,
        )
        update_sell_lock_status(tx_hash, "released", eth_tx_hash=eth_hash, release_nonce=nonce)

    @pytest.mark.asyncio
    async def test_two_rows_ready_one_sweep_per_poll(self, sell_env, monkeypatch):
        """Two settle-ready rows in one poll: the first sweeps, the second
        waits until the first is sealed — never two escrow sends at once."""
        h1, h2 = "0x" + "a1" * 32, "0x" + "a2" * 32
        e1, e2 = "0x" + "1a" * 32, "0x" + "2a" * 32
        self._released_row(h1, e1, 7)
        self._released_row(h2, e2, 8)
        monkeypatch.setattr(
            wdm,
            "_eth_rpc",
            _eth_rpc_stub(
                receipts={
                    e1: {"status": "0x1", "blockNumber": hex(450)},
                    e2: {"status": "0x1", "blockNumber": hex(450)},
                },
                nonces={"latest": 9, "pending": 9},
                block=460,
            ),
        )

        await sellmon.poll_sells_once()
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["nonce"] == 0
        r1, r2 = get_sell_lock_by_ait_tx_hash(h1), get_sell_lock_by_ait_tx_hash(h2)
        assert r1["status"] == "settling"  # in flight — not settled on broadcast
        assert r2["status"] == "released"  # deferred — the slot was busy

        # Seal the first; the second may now start its own sweep.
        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref=h1, to=TEST_TREASURY, ait=Decimal("10"), nonce=0)]
        sell_env["escrow_nonce"] = 1
        await sellmon.poll_sells_once()
        r1, r2 = get_sell_lock_by_ait_tx_hash(h1), get_sell_lock_by_ait_tx_hash(h2)
        assert r1["status"] == "settled"
        assert r2["status"] == "settling"
        assert len(sell_env["ait_sends"]) == 2
        assert sell_env["ait_sends"][1]["nonce"] == 1  # fresh nonce post-seal

        sell_env["transfers"] = [_sealed_sweep_tx(sell_ref=h2, to=TEST_TREASURY, ait=Decimal("10"), nonce=1)]
        sell_env["escrow_nonce"] = 2
        await sellmon.poll_sells_once()
        assert get_sell_lock_by_ait_tx_hash(h1)["status"] == "settled"
        assert get_sell_lock_by_ait_tx_hash(h2)["status"] == "settled"
        assert len(sell_env["ait_sends"]) == 2  # exactly one payment each


class TestEscrowFeeFloat:
    """The escrow pays amount + 0.01 AIT fee per sweep; a short balance
    parks the row visibly instead of failing or signing blind."""

    @pytest.mark.asyncio
    async def test_settle_parks_on_fee_deficit_then_resumes(self, sell_env):
        insert_sell_lock(
            ait_tx_hash="0x" + "f1" * 32,
            shop_ait_address=SHOP_AIT,
            shop_eth_address=SHOP_ETH,
            amount_ait=Decimal("10"),
            eth_amount=Decimal("0.0009"),
            status="released",
            locked_height=900,
        )
        # Escrow holds the locked 10 AIT but nothing for the fee.
        sell_env["escrow_balance"] = Decimal("10")

        async def _sent(row):  # bypass the ETH re-verify for this unit
            await sellmon._settle_lock(sellmon._sell_config(), row)

        row = get_sell_lock_by_ait_tx_hash("0x" + "f1" * 32)
        await _sent(row)
        row = get_sell_lock_by_ait_tx_hash("0x" + "f1" * 32)
        assert row["status"] == "queued_fee_settle"
        assert "fee float deficit" in (row["error"] or "")
        assert "0.01" in (row["error"] or "")
        assert not sell_env["ait_sends"]

        # Operator seeds the fee float; the next attempt proceeds.
        sell_env["escrow_balance"] = Decimal("10.5")
        await sellmon._settle_lock(sellmon._sell_config(), row)
        row = get_sell_lock_by_ait_tx_hash("0x" + "f1" * 32)
        assert row["status"] == "settling"
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["fee"] == 360_000  # 0.01 AIT units

    @pytest.mark.asyncio
    async def test_refund_parks_on_fee_deficit(self, sell_env, monkeypatch):
        sell_env["escrow_balance"] = Decimal("10")  # locked 10, no fee float
        sell_env["transfers"] = [_lock_tx(None, tx_hash="0x" + "f2" * 32, height=100)]
        sell_env["chain_height"] = 300

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "f2" * 32)
        assert row["status"] == "queued_fee_refund"
        assert "fee float deficit" in (row["error"] or "")
        assert not sell_env["ait_sends"]

        # Refill -> handler retries the refund with the original reason.
        sell_env["escrow_balance"] = Decimal("11")
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "f2" * 32)
        assert row["status"] == "refunding"
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT

    @pytest.mark.asyncio
    async def test_reparked_refund_keeps_original_reason(self, sell_env):
        """Re-parking must not accumulate the deficit marker: the reason
        carried into the signed refund tx is the row's original reason,
        split at the shared marker — never the grown error string."""
        sell_env["escrow_balance"] = Decimal("10")  # locked 10, no fee float
        sell_env["transfers"] = [_lock_tx(None, tx_hash="0x" + "f3" * 32, height=100)]
        sell_env["chain_height"] = 300

        for _ in range(3):
            await sellmon.poll_sells_once()
            row = get_sell_lock_by_ait_tx_hash("0x" + "f3" * 32)
            assert row["status"] == "queued_fee_refund"
            error = row["error"] or ""
            assert error.count("escrow fee float deficit") == 1
            assert error.startswith("orphan lock — no matching quote")

        # Funded: the sweep proceeds carrying the ORIGINAL reason on-chain.
        sell_env["escrow_balance"] = Decimal("11")
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "f3" * 32)
        assert row["status"] == "refunding"
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT
        assert sell_env["ait_sends"][0]["payload"]["reason"] == "orphan lock — no matching quote"


class TestConfigSafety:
    def test_missing_chain_id_refuses(self, sell_env, monkeypatch):
        """No CHAIN_ID env -> the monitor refuses to sign rather than fall
        back to ait-localnet."""
        monkeypatch.delenv("CHAIN_ID", raising=False)
        enabled, reason = sellmon.sell_config_status()
        assert not enabled
        assert "CHAIN_ID" in reason

    @pytest.mark.asyncio
    async def test_missing_chain_id_poll_skips(self, sell_env, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        result = await sellmon.poll_sells_once()
        assert result["skipped"] is True
        assert "CHAIN_ID" in result["reason"]

    @pytest.mark.asyncio
    async def test_scan_fetches_unbounded(self, sell_env):
        """The lock scan requests limit=0 — the endpoint's unbounded mode —
        so a poll can never page-truncate away a lock."""
        await sellmon.poll_sells_once()
        assert sell_env["scan_limits"]  # the scan ran
        assert all(limit == 0 for limit in sell_env["scan_limits"])


class TestSellRoutes:
    """Route-level validation for the sell endpoints."""

    @pytest.fixture
    def client(self, sell_env, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from wallet_app.bridge.bridge_routes import bridge_router
        from wallet_app.deps import require_admin_api_key

        app = FastAPI()
        app.include_router(bridge_router)
        app.dependency_overrides[require_admin_api_key] = lambda: None
        return TestClient(app)

    def test_quote_returns_required_shape(self, client):
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("quote_id", "rate", "fee_ait", "eth_amount", "expires_at"):
            assert key in body, f"missing {key}"
        assert body["escrow_address"]
        quote = get_sell_quote(body["quote_id"])
        assert quote["status"] == "quoted"

    def test_quote_rejects_negative_amount(self, client):
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "-5", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 400

    def test_quote_rejects_missing_eth_address(self, client):
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 400

    def test_quote_rejects_bad_eth_address(self, client):
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": "not-an-address", "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 400

    def test_quote_rejects_non_numeric_amount(self, client):
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "lots", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 400

    def test_quote_503_when_disabled(self, client, monkeypatch):
        monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 503

    def test_quote_503_on_stale_feed(self, client, monkeypatch):
        async def _stale():
            return None

        monkeypatch.setattr(sellmon, "get_eth_prices_fresh", _stale)
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 503

    def test_status_and_list(self, client):
        quote_id = _insert_quote()
        resp = client.get(f"/v1/bridge/sell/status/{quote_id}")
        assert resp.status_code == 200
        assert resp.json()["kind"] == "quote"
        assert resp.json()["quote_id"] == quote_id

        resp = client.get("/v1/bridge/sell/status/0xnonexistent")
        assert resp.status_code == 404

        resp = client.get("/v1/bridge/sell/list")
        assert resp.status_code == 200
        assert len(resp.json()["quotes"]) == 1

    def test_quote_open_cap_429(self, client, monkeypatch):
        monkeypatch.setenv("SELL_MAX_OPEN_QUOTES_PER_SHOP", "2")
        monkeypatch.setenv("SELL_QUOTE_MIN_INTERVAL_SECONDS", "0")
        for _ in range(2):
            resp = client.post(
                "/v1/bridge/sell/quote",
                json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
            )
            assert resp.status_code == 200
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 429

    def test_quote_rate_limit_429(self, client, monkeypatch):
        monkeypatch.setenv("SELL_QUOTE_MIN_INTERVAL_SECONDS", "3600")
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 200
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 429

    def test_quote_503_when_flag_off(self, client, monkeypatch):
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "false")
        resp = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": "10", "eth_address": SHOP_ETH, "ait_address": SHOP_AIT},
        )
        assert resp.status_code == 503
        assert "disabled" in resp.json()["detail"].lower()


class TestStatusHandlerDispatch:
    """The status->handler table must cover every open sell-lock status except
    needs_review_sweep (deliberately terminal for the machine)."""

    def test_handler_table_covers_open_statuses(self):
        assert set(sellmon._SELL_STATUS_HANDLERS) == set(_SELL_OPEN_STATUSES) - {"needs_review_sweep"}


class TestEthAmountStorage:
    """ETH-10c: eth_amount is TEXT affinity storing a plain-decimal string —
    never a REAL float; legacy NUMERIC rows still parse."""

    def test_quote_eth_amount_stores_plain_decimal_text(self, sell_env):
        """A tiny quote (0.01 AIT ≈ 9.3e-7 ETH — the exact case str() would
        render in scientific notation) must persist as plain TEXT."""
        from wallet_app.bridge import bridge_db as db

        quote_id = _insert_quote(ait_amount=Decimal("0.01"))
        conn = db._connect_db()
        try:
            kind, value = conn.execute(
                "SELECT typeof(eth_amount), eth_amount FROM bridge_sell_quotes WHERE id = ?", (quote_id,)
            ).fetchone()
        finally:
            conn.close()
        assert kind == "text"
        assert value == "0.00000093"  # format(v, 'f'), not the REAL '9.3e-07'
        assert "e" not in value.lower()

    def test_lock_eth_amount_stores_plain_decimal_text(self, sell_env):
        """The lock row (where the amount actually pays out) gets the same
        TEXT form — via insert and via the status update path."""
        from wallet_app.bridge import bridge_db as db

        h = "0x" + "cc" * 32
        insert_sell_lock(
            ait_tx_hash=h, shop_ait_address=SHOP_AIT, amount_ait=Decimal("0.01"), eth_amount=Decimal("0.00000093")
        )
        update_sell_lock_status(h, "released", eth_amount=Decimal("9.3e-7"))
        conn = db._connect_db()
        try:
            kind, value = conn.execute(
                "SELECT typeof(eth_amount), eth_amount FROM bridge_sell_locks WHERE ait_tx_hash = ?", (h,)
            ).fetchone()
        finally:
            conn.close()
        assert kind == "text"
        assert value == "0.00000093"

    def test_legacy_numeric_row_still_prices_a_lock(self, sell_env, tmp_path):
        """A row persisted by an old binary — NUMERIC column holding a REAL —
        still parses through the converter and prices its lock."""
        from wallet_app.bridge import bridge_db as db

        legacy = tmp_path / "legacy.db"
        conn = db._connect_db(str(legacy))
        conn.execute("CREATE TABLE legacy (ait_amount NUMERIC, eth_amount NUMERIC)")
        conn.execute("INSERT INTO legacy VALUES (?, ?)", (Decimal("0.05"), Decimal("0.00000510899882107927")))
        conn.commit()
        row = conn.execute("SELECT ait_amount, eth_amount FROM legacy").fetchone()
        conn.close()

        quote = {"ait_amount": row[0], "eth_amount": row[1]}
        priced = sellmon._eth_for_lock_at_quote(Decimal("0.05"), quote)
        assert priced == Decimal("0.00000510899882107927")

    def test_daily_cap_boundary_on_text_rows(self, sell_env):
        """Operator-pinned boundary: 0.02 committed + 0.01 incoming is admitted
        at the 0.03/day cap; anything more is refused. The SUM runs over TEXT
        values, so this also proves aggregate reads still coerce."""
        for i, amount in enumerate(("0.015", "0.005")):
            h = "0x" + str(i) * 64
            insert_sell_lock(ait_tx_hash=h, shop_ait_address=SHOP_AIT, amount_ait=Decimal("10"), status="locked")
            update_sell_lock_status(h, "released", eth_amount=Decimal(amount))
            update_sell_lock_status(h, "settled")

        committed = get_sell_eth_committed_since((datetime.now() - timedelta(hours=1)).isoformat())
        assert committed == Decimal("0.02")
        cap = Decimal("0.03")  # SELL_MAX_ETH_PER_DAY default
        assert not committed + Decimal("0.01") > cap  # 0.02 + 0.01 admitted
        assert committed + Decimal("0.0100001") > cap  # anything more refused


@pytest.mark.asyncio
async def test_fee_deficit_warning_logs_once_per_deficit(sell_env, caplog):
    """Log-once for the fee-float WARNING (wallet log-once row, pending
    registration): while the same deficit keeps a lock parked, every poll
    currently re-emits "escrow fee float short" at WARNING — journal noise
    that feeds the JournalErrors alert. One warning per deficit state;
    a deficit that CHANGES may warn again."""
    import logging

    insert_sell_lock(
        ait_tx_hash="0x" + "f3" * 32,
        shop_ait_address=SHOP_AIT,
        shop_eth_address=SHOP_ETH,
        amount_ait=Decimal("10"),
        eth_amount=Decimal("0.0009"),
        status="released",
        locked_height=900,
    )
    sell_env["escrow_balance"] = Decimal("10")  # locked 10, nothing for the fee

    caplog.set_level(logging.WARNING)
    cfg = sellmon._sell_config()
    row = get_sell_lock_by_ait_tx_hash("0x" + "f3" * 32)
    await sellmon._settle_lock(cfg, row)
    row = get_sell_lock_by_ait_tx_hash("0x" + "f3" * 32)
    await sellmon._settle_lock(cfg, row)  # second poll, same deficit

    warns = [r for r in caplog.records if r.levelno >= logging.WARNING and "fee float short" in r.getMessage()]
    assert len(warns) == 1
