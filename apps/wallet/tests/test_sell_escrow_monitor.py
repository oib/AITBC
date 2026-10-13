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
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from wallet_app.bridge import bridge_withdraw_monitor as wdm
from wallet_app.bridge import sell_escrow_monitor as sellmon
from wallet_app.bridge.bridge_db import (
    get_sell_lock_by_ait_tx_hash,
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
):
    """Dispatch wdm._eth_rpc calls used by the release-outcome checks."""
    receipts = receipts or {}
    txs = txs or {}
    nonces = nonces or {"latest": 0, "pending": 0}

    async def _stub(method: str, params: list[Any]) -> Any:
        if method == "eth_getTransactionReceipt":
            return receipts.get(params[0])
        if method == "eth_getTransactionByHash":
            return txs.get(params[0])
        if method == "eth_blockNumber":
            return hex(block)
        if method == "eth_getTransactionCount":
            return hex(nonces.get(params[1], 0))
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
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:0")
    monkeypatch.delenv("SELL_MAX_ETH_PER_TX", raising=False)
    monkeypatch.delenv("SELL_MAX_ETH_PER_DAY", raising=False)
    monkeypatch.delenv("SELL_RELEASE_DEADLINE", raising=False)
    monkeypatch.delenv("SELL_LOCK_ORPHAN_BLOCKS", raising=False)
    monkeypatch.delenv("ETH_WITHDRAW_MIN_RESERVE", raising=False)

    monkeypatch.setattr(wdm, "BRIDGE_ENABLED", True)
    monkeypatch.setattr(wdm, "ETH_WALLET_ADDRESS", TEST_ETH_ADDRESS)
    monkeypatch.setattr(wdm, "ETH_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
    monkeypatch.setattr(wdm, "BRIDGE_ADMIN_PRIVATE_KEY", "")
    monkeypatch.setattr(wdm, "ETH_WITHDRAW_GAS", 100_000)
    monkeypatch.setattr(wdm, "BLOCKCHAIN_RPC_URL", "http://localhost:0")

    async def _coro(value):
        return value

    monkeypatch.setattr(wdm, "_eth_balance", lambda address: _coro(Decimal("0.1")))
    monkeypatch.setattr(wdm, "_eth_gas_price", lambda: _coro(1_000_000_000))
    monkeypatch.setattr(wdm, "_eth_nonce", lambda address: _coro(7))
    monkeypatch.setattr(wdm, "_eth_rpc", _eth_rpc_stub())

    state = {"eth_sends": [], "ait_sends": [], "escrow_nonce": 0, "chain_height": 1000}

    async def _broadcast(raw: str) -> str:
        state["eth_sends"].append(raw)
        return "0x" + "ee" * 32

    async def _ait_broadcast(tx: dict) -> str:
        state["ait_sends"].append(tx)
        return "0x" + "ff" * 32

    async def _account_nonce(address: str) -> int:
        return int(state["escrow_nonce"])

    async def _transfers(address: str, limit: int = 500) -> list[dict]:
        return list(state.get("transfers", []))

    async def _height() -> int:
        return int(state["chain_height"])

    monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast)
    monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _ait_broadcast)
    monkeypatch.setattr(sellmon, "_account_nonce", _account_nonce)
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


def _lock_tx(quote_id: str | None, tx_hash: str | None = None, height: int = 900, ait: Decimal = Decimal("10")) -> dict:
    from aitbc.utils import ait_to_units

    return {
        "tx_hash": tx_hash or "0x" + "aa" * 32,
        "sender": SHOP_AIT,
        "recipient": _escrow_address(),
        "value": ait_to_units(ait),
        "payload": {"sell_quote": quote_id} if quote_id else {},
        "block_height": height,
        "nonce": 1,
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


class TestQuoteAndLockMatching:
    @pytest.mark.asyncio
    async def test_lock_with_live_quote_releases(self, sell_env):
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        result = await sellmon.poll_sells_once()
        assert result["recorded"] == 1
        assert len(sell_env["eth_sends"]) == 1

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "released"
        assert row["quote_id"] == quote_id
        assert row["eth_tx_hash"]
        assert row["release_nonce"] == 7
        assert get_sell_quote(quote_id)["status"] == "locked"

    @pytest.mark.asyncio
    async def test_lock_on_expired_quote_requotes(self, sell_env):
        quote_id = _insert_quote(expired=True)
        sell_env["transfers"] = [_lock_tx(quote_id)]

        result = await sellmon.poll_sells_once()
        assert result["recorded"] == 1
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["requoted"] == 1
        assert row["eth_amount"] is not None
        assert row["status"] == "released"
        assert get_sell_quote(quote_id)["status"] == "expired"

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

        sell_env["chain_height"] = 300  # 200 blocks > SELL_LOCK_ORPHAN_BLOCKS=150
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "bb" * 32)
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"] == "0x" + "ff" * 32
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT

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
        assert first["status"] == "released"
        assert second["status"] == "orphaned"
        assert len(sell_env["eth_sends"]) == 1


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
        assert row["status"] == "released"
        assert len(sell_env["eth_sends"]) == 1

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
        assert row["status"] == "released"
        assert len(sell_env["eth_sends"]) == 1


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
            raise AssertionError(method)

        monkeypatch.setattr(wdm, "_eth_rpc", _eth_rpc)
        monkeypatch.setattr(sellmon, "update_sell_lock_status", _flaky_update)
        await sellmon.poll_sells_once()
        # DB recovered — real updater again.
        monkeypatch.setattr(sellmon, "update_sell_lock_status", real_update)

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "releasing"
        assert row["eth_tx_hash"]
        assert not sell_env["ait_sends"]  # no refund despite the failure

        # Resume pass: 'sent' -> released; next poll settles the escrow leg.
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "released"

        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "settled"
        assert row["settle_tx_hash"] == "0x" + "ff" * 32
        # Exactly one AIT leg: the settle. No refund was ever sent.
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == TEST_TREASURY
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
        # release never reached chain -> failed + escrow refund issued
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"]
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT

    @pytest.mark.asyncio
    async def test_refund_failure_marks_failed_no_second_refund(self, sell_env, monkeypatch):
        quote_id = _insert_quote()
        sell_env["transfers"] = [_lock_tx(quote_id)]

        async def _broadcast_fail(raw):
            raise RuntimeError("node rejected")

        async def _ait_fail(tx):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast_fail)
        monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _ait_fail)
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "aa" * 32)
        assert row["status"] == "failed"

        # A second poll never re-issues the refund.
        sell_env["transfers"] = []
        await sellmon.poll_sells_once()
        assert len(sell_env["ait_sends"]) == 0

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
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"]
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["to"] == SHOP_AIT
        assert not sell_env["eth_sends"]

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
        recovered by its escrow nonce — settled once, never re-sent."""
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
            {
                "tx_hash": "0x" + "99" * 32,
                "sender": sell_env["escrow"],
                "recipient": TEST_TREASURY,
                "nonce": 5,
                "block_height": 910,
                "type": "TRANSFER",
                "payload": {},
            }
        ]
        await sellmon.poll_sells_once()

        row = get_sell_lock_by_ait_tx_hash("0x" + "ee" * 32)
        assert row["status"] == "settled"
        assert row["settle_tx_hash"] == "0x" + "99" * 32
        assert not sell_env["ait_sends"]  # recovered by nonce, not re-sent

    @pytest.mark.asyncio
    async def test_settling_row_nonce_free_resends_once(self, sell_env):
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

        await sellmon.poll_sells_once()
        row = get_sell_lock_by_ait_tx_hash("0x" + "ef" * 32)
        assert row["status"] == "settled"
        # Re-broadcast of the STORED blob — never a re-signed new nonce.
        assert len(sell_env["ait_sends"]) == 1
        assert sell_env["ait_sends"][0]["nonce"] == 5


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
