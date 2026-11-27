"""#3043 AUDIT-BRIDGE-ESCROW-SWEEP-REBROADCAST-1: bounded escrow sweep
re-broadcasts with terminal escalation.

A sweep blob the mempool never admits used to re-broadcast every poll
forever — one stuck row head-of-line blocked every escrow settlement in
BOTH lanes (the inflight union spans sell locks and exchange settlements).
Pins:

- an unlandable blob reaches ``needs_review_sweep`` after the persisted
  ``sweep_rebroadcasts`` budget and stops being re-broadcast;
- the row drops out of the inflight set so the lane unblocks;
- a fresh intent (``_escrow_sweep``) resets the budget;
- the exchange lane's inflight probe fails closed on store errors.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from wallet_app.bridge import bridge_db
from wallet_app.bridge import exchange_settlement_driver as esd
from wallet_app.bridge import sell_escrow_monitor as sellmon
from wallet_app.bridge import sell_escrow_settlement as ses
from wallet_app.bridge.bridge_db import (
    get_exchange_inflight_sweep,
    get_exchange_settlement,
    get_sell_inflight_sweep,
    get_sell_lock_by_ait_tx_hash,
    init_db,
    insert_exchange_settlement,
    insert_sell_lock,
    update_exchange_settlement,
    update_sell_lock_status,
)

H = "0x" + "ab" * 32
BLOB = json.dumps({"type": "TRANSFER", "nonce": 5, "to": "0x" + "d" * 40})
TREASURY = "0x" + "33" * 40
ESCROW = "0x" + "bb" * 40
SHOP = "0x" + "44" * 40


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Throwaway bridge DB + chain-surface stubs shared by both lanes."""
    monkeypatch.setattr(bridge_db, "DB_PATH", str(tmp_path / "bridge.db"))
    init_db()
    monkeypatch.setenv("ESCROW_SWEEP_MAX_REBROADCASTS", "3")

    state = {"broadcasts": []}

    async def _account_view(address: str):
        # Account nonce == intent nonce → the slot is still free.
        return 5, Decimal("1000")

    async def _broadcast(tx):
        state["broadcasts"].append(tx)
        return "0x" + "cc" * 32

    async def _no_outflow(*args, **kwargs):
        return None

    monkeypatch.setattr(sellmon, "_account_view", _account_view)
    monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _broadcast)
    monkeypatch.setattr(ses, "_find_escrow_outflow", _no_outflow)
    monkeypatch.setattr(esd, "_find_escrow_outflow", _no_outflow)
    return state


def _sell_cfg():
    return SimpleNamespace(escrow_address=ESCROW, treasury_address=TREASURY, sell_seal_depth=3)


def _exchange_cfg():
    return SimpleNamespace(
        escrow=SimpleNamespace(escrow_address=ESCROW, treasury_address=TREASURY),
        seal_depth=3,
    )


def _settling_sell_row(rebroadcasts: int = 0) -> dict:
    insert_sell_lock(
        ait_tx_hash=H,
        shop_ait_address=SHOP,
        amount_ait=Decimal("10"),
        status="released",
        locked_height=900,
    )
    update_sell_lock_status(
        H,
        "settling",
        escrow_out_nonce=5,
        escrow_out_tx=BLOB,
        sweep_rebroadcasts=rebroadcasts,
        expected_statuses={"released"},
    )
    row = get_sell_lock_by_ait_tx_hash(H)
    assert row is not None
    return row


def _refunding_settlement(rebroadcasts: int = 0) -> dict:
    sid = insert_exchange_settlement(
        "trade",
        42,
        buyer_address="0x" + "55" * 40,
        seller_address=SHOP,
        amount_ait=Decimal("10"),
        fee_ait=Decimal("0.05"),
    )
    assert sid is not None
    update_exchange_settlement(
        sid,
        "refunding",
        escrow_out_nonce=5,
        escrow_out_tx=BLOB,
        sweep_rebroadcasts=rebroadcasts,
        expected_statuses={"locked"},
    )
    row = get_exchange_settlement("trade", 42)
    assert row is not None
    return row


class TestSellLaneBudget:
    @pytest.mark.asyncio
    async def test_unlandable_blob_escalates_and_unblocks(self, ledger, caplog):
        import logging

        row = _settling_sell_row(rebroadcasts=3)  # budget already spent
        with caplog.at_level(logging.CRITICAL):
            await ses._resolve_escrow_sweep(_sell_cfg(), row)

        fresh = get_sell_lock_by_ait_tx_hash(H)
        assert fresh["status"] == "needs_review_sweep"
        assert "unlandable" in (fresh["error"] or "")
        assert not ledger["broadcasts"]  # no re-broadcast past the cap
        assert any("unlandable" in r.getMessage() for r in caplog.records if r.levelno >= logging.CRITICAL)
        # The stuck row dropped out of the inflight set — the lane unblocks.
        assert get_sell_inflight_sweep() is None
        assert get_exchange_inflight_sweep() is None

    @pytest.mark.asyncio
    async def test_rebroadcasts_count_and_bound(self, ledger):
        _settling_sell_row(rebroadcasts=0)
        for expected in (1, 2, 3):
            row = get_sell_lock_by_ait_tx_hash(H)
            await ses._resolve_escrow_sweep(_sell_cfg(), row)
            fresh = get_sell_lock_by_ait_tx_hash(H)
            assert fresh["status"] == "settling"
            assert fresh["sweep_rebroadcasts"] == expected
        assert len(ledger["broadcasts"]) == 3

        # Fourth pass: budget spent → terminal, no fourth broadcast.
        row = get_sell_lock_by_ait_tx_hash(H)
        await ses._resolve_escrow_sweep(_sell_cfg(), row)
        fresh = get_sell_lock_by_ait_tx_hash(H)
        assert fresh["status"] == "needs_review_sweep"
        assert len(ledger["broadcasts"]) == 3
        assert get_sell_inflight_sweep() is None

    @pytest.mark.asyncio
    async def test_fresh_intent_resets_budget(self, ledger, monkeypatch):
        row = _settling_sell_row(rebroadcasts=7)
        # Drive the row back to a pre-sweep state carrying a spent budget.
        update_sell_lock_status(H, "released", sweep_rebroadcasts=7, expected_statuses={"settling"})
        row = get_sell_lock_by_ait_tx_hash(H)
        assert row["status"] == "released" and row["sweep_rebroadcasts"] == 7

        async def _ok_lock(r):
            return "ok", {}

        async def _sign(cfg, to, amount, extra, nonce):
            return {"type": "TRANSFER", "nonce": nonce}

        monkeypatch.setattr(ses, "_check_inbound_lock", _ok_lock)
        monkeypatch.setattr(ses, "_sign_escrow_transfer", _sign)

        outcome = await ses._escrow_sweep(_sell_cfg(), row, TREASURY, "sell_settle", "settling", "queued_fee_settle")
        assert outcome == "sent"
        fresh = get_sell_lock_by_ait_tx_hash(H)
        assert fresh["status"] == "settling"
        assert fresh["sweep_rebroadcasts"] == 0

    @pytest.mark.asyncio
    async def test_rebroadcast_count_cas_loss_skips_broadcast(self, ledger):
        row = _settling_sell_row(rebroadcasts=0)
        # Row moves on between the snapshot and the count write.
        update_sell_lock_status(H, "needs_review_sweep", expected_statuses={"settling"})
        await ses._resolve_escrow_sweep(_sell_cfg(), row)
        assert not ledger["broadcasts"]


class TestExchangeLaneBudget:
    @pytest.mark.asyncio
    async def test_unlandable_blob_escalates_and_unblocks(self, ledger, caplog):
        import logging

        row = _refunding_settlement(rebroadcasts=3)
        with caplog.at_level(logging.CRITICAL):
            await esd._resolve_sweep(_exchange_cfg(), row)

        fresh = get_exchange_settlement("trade", 42)
        assert fresh["status"] == "needs_review_sweep"
        assert "unlandable" in (fresh["error"] or "")
        assert not ledger["broadcasts"]
        assert any("unlandable" in r.getMessage() for r in caplog.records if r.levelno >= logging.CRITICAL)
        assert get_exchange_inflight_sweep() is None
        assert get_sell_inflight_sweep() is None

    @pytest.mark.asyncio
    async def test_rebroadcasts_count_and_bound(self, ledger):
        _refunding_settlement(rebroadcasts=0)
        for expected in (1, 2, 3):
            row = get_exchange_settlement("trade", 42)
            await esd._resolve_sweep(_exchange_cfg(), row)
            fresh = get_exchange_settlement("trade", 42)
            assert fresh["status"] == "refunding"
            assert fresh["sweep_rebroadcasts"] == expected
        assert len(ledger["broadcasts"]) == 3

        row = get_exchange_settlement("trade", 42)
        await esd._resolve_sweep(_exchange_cfg(), row)
        fresh = get_exchange_settlement("trade", 42)
        assert fresh["status"] == "needs_review_sweep"
        assert len(ledger["broadcasts"]) == 3
        assert get_exchange_inflight_sweep() is None

    @pytest.mark.asyncio
    async def test_fresh_intent_resets_budget(self, ledger, monkeypatch):
        sid_row = _refunding_settlement(rebroadcasts=7)
        # Back to a pre-sweep state carrying a spent budget.
        update_exchange_settlement(sid_row["id"], "refund_pending", sweep_rebroadcasts=7, expected_statuses={"refunding"})
        row = get_exchange_settlement("trade", 42)
        assert row["status"] == "refund_pending" and row["sweep_rebroadcasts"] == 7

        async def _sign(cfg, to, amount, extra, nonce):
            return {"type": "TRANSFER", "nonce": nonce}

        monkeypatch.setattr(esd, "_inflight_sweep", lambda *a, **k: False)
        monkeypatch.setattr(sellmon, "_sign_escrow_transfer", _sign)

        outcome = await esd._escrow_sweep(_exchange_cfg(), row, "refunding", "queued_fee_refund")
        assert outcome == "sent"
        fresh = get_exchange_settlement("trade", 42)
        assert fresh["status"] == "refunding"
        assert fresh["sweep_rebroadcasts"] == 0


class TestInflightProbeFailClosed:
    def test_probe_failure_defers_sell_sweep(self, ledger, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")

        def _boom():
            raise RuntimeError("db gone")

        monkeypatch.setattr(bridge_db, "get_exchange_inflight_sweep", _boom)
        assert ses._exchange_inflight_sweep() is True  # fail closed → defer

    def test_probe_disabled_and_empty_stay_open(self, ledger, monkeypatch):
        # Disabled exchange lane → not in-flight regardless of the probe.
        monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)
        assert ses._exchange_inflight_sweep() is False

        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
        assert ses._exchange_inflight_sweep() is False  # empty table → no sweep in flight
