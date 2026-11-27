"""Pins for AUDIT-RESERVE-FAILOPEN-1 (#3072).

``_pending_eth_reserve`` is the float gate every ETH payout lane sizes
against. Its terms used to fail open: any read error coerced to zero, so
a database fault made custodied liabilities invisible exactly when the
control mattered — payouts would spend money the ledger could not see.

The fix makes each term three-state: unprovisioned (``no such table``
on a pre-feature database, or an absent exchange.db) is legitimately
zero; healthy returns the value; UNKNOWN — any other read failure —
raises :class:`ReserveUnknownError` after a CRITICAL log, and every
payout lane lets it propagate (fail closed).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from wallet_app.bridge import bridge_db, bridge_withdraw_monitor as wdm
from wallet_app.bridge.bridge_db import init_db, insert_withdrawal

NODE_A = "0x" + "aa" * 20


def _bridge_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "bridge_deposits.db"
    monkeypatch.setattr("wallet_app.bridge.bridge_db.DB_PATH", str(db))
    init_db()
    return db


def _no_exchange_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{tmp_path}/absent/exchange.db")


def _withdrawal(bridge_db_path: Path) -> None:
    insert_withdrawal(
        ait_tx_hash="0x" + "11" * 32,
        from_address="0x" + "22" * 20,
        eth_address="0x" + "33" * 20,
        amount_ait=Decimal("10"),
        fee_ait=Decimal("0.05"),
        net_ait=Decimal("9.95"),
        amount_eth=Decimal("0.2"),
    )


class TestUnknownTermsFailClosed:
    def test_corrupt_exchange_db_makes_reserve_unknown(self, tmp_path, monkeypatch):
        """Headline: a corrupt exchange.db must not silently zero the
        prepaid term — the whole reserve reports UNKNOWN."""
        _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)
        bad = tmp_path / "exchange.db"
        bad.write_bytes(b"not a sqlite database" * 100)
        monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{bad}")
        with pytest.raises(wdm.ReserveUnknownError):
            wdm._pending_eth_reserve()

    def test_exchange_db_missing_prepaid_tables_is_unknown(self, tmp_path, monkeypatch):
        """exchange.db exists but lacks prepaid_deposits/debits — schema
        mismatch mid-deploy, not an unprovisioned node."""
        _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)
        db = tmp_path / "exchange.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
        conn.commit()
        conn.close()
        monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{db}")
        with pytest.raises(wdm.ReserveUnknownError):
            wdm._pending_eth_reserve()

    def test_sell_term_read_failure_is_unknown(self, tmp_path, monkeypatch):
        """Any non-missing-table failure on the sell term — lock
        contention, IO error — propagates as UNKNOWN."""
        _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)

        def boom(**kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(bridge_db, "get_sell_pending_eth_reserve", boom)
        with pytest.raises(wdm.ReserveUnknownError):
            wdm._pending_eth_reserve()

    def test_exchange_settlement_term_read_failure_is_unknown(self, tmp_path, monkeypatch):
        _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)

        def boom(**kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(bridge_db, "get_exchange_pending_eth_reserve", boom)
        with pytest.raises(wdm.ReserveUnknownError):
            wdm._pending_eth_reserve()

    def test_withdraw_term_read_failure_is_unknown(self, tmp_path, monkeypatch):
        """The core withdrawals table failing is unknown too — the old
        code let it propagate raw; now it is a named, logged fault."""
        _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)

        def boom():
            raise sqlite3.DatabaseError("file is not a database")

        monkeypatch.setattr(bridge_db, "get_pending_withdrawals", boom)
        with pytest.raises(wdm.ReserveUnknownError):
            wdm._pending_eth_reserve()

    def test_corrupt_bridge_db_is_unknown(self, tmp_path, monkeypatch):
        """End-to-end: garbage in the wallet's own bridge.db."""
        db = tmp_path / "bridge_deposits.db"
        db.write_bytes(b"garbage" * 200)
        monkeypatch.setattr("wallet_app.bridge.bridge_db.DB_PATH", str(db))
        _no_exchange_db(tmp_path, monkeypatch)
        with pytest.raises(wdm.ReserveUnknownError):
            wdm._pending_eth_reserve()


class TestUnprovisionedStaysZero:
    def test_missing_sell_and_exchange_tables_are_zero(self, tmp_path, monkeypatch):
        """A pre-ETH-10/pre-phase-3 database legitimately lacks the sell
        and settlement tables — ``no such table`` stays zero, and the
        healthy withdrawals term still reserves."""
        db = tmp_path / "bridge_deposits.db"
        monkeypatch.setattr("wallet_app.bridge.bridge_db.DB_PATH", str(db))
        init_db()
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE bridge_sell_locks")
        conn.execute("DROP TABLE exchange_settlements")
        conn.commit()
        conn.close()
        _no_exchange_db(tmp_path, monkeypatch)
        _withdrawal(db)
        assert wdm._pending_eth_reserve() == Decimal("0.2")

    def test_missing_exchange_db_keeps_reserve_working(self, tmp_path, monkeypatch):
        """Unprovisioned exchange node: prepaid term is zero, the rest sums."""
        bridge = _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)
        _withdrawal(bridge)
        assert wdm._pending_eth_reserve() == Decimal("0.2")


class TestNoBypassLane:
    """Coverage proof: every ETH outbound lane sizes against the reserve.

    ``_broadcast_release_tx`` is the single ETH-send primitive; each of
    its three callers must compute ``available`` through
    ``_pending_eth_reserve`` — a lane that skipped it would spend the
    shared float without seeing custodied liabilities."""

    _LANES = (
        "bridge_withdraw_monitor.py",
        "sell_escrow_settlement.py",
        "exchange_settlement_driver.py",
    )

    def test_all_release_lanes_size_against_reserve(self):
        root = Path(wdm.__file__).parent
        for name in self._LANES:
            src = (root / name).read_text()
            assert "_pending_eth_reserve(" in src, f"{name} has an ETH release lane that bypasses the reserve"

    def test_unknown_reserve_never_reaches_refund_resolvers(self):
        """#3072: ReserveUnknownError is a PRE-FLIGHT fault — nothing was
        signed or broadcast — so it must bypass the release-failure
        resolvers, which verify 'not_sent' and pay out refunds. Each
        lane's release try must catch it BEFORE the broad handler that
        routes into its resolver."""
        root = Path(wdm.__file__).parent
        guards = (
            ("bridge_withdraw_monitor.py", "except ReserveUnknownError", "await _resolve_release_failure("),
            ("sell_escrow_settlement.py", "except wdm.ReserveUnknownError", "await _resolve_lock_release_failure("),
            ("exchange_settlement_driver.py", "except wdm.ReserveUnknownError", "await _resolve_release_failure("),
        )
        for name, guard, resolver in guards:
            src = (root / name).read_text()
            assert guard in src, f"{name}: no ReserveUnknownError guard on the release path"
            assert src.index(guard) < src.index(resolver), (
                f"{name}: ReserveUnknownError guard must precede the {resolver} call site"
            )
        # The withdraw lane has TWO release entry points (fresh price-and-
        # release, awaiting-depth drain) plus the pending-release drain
        # that makes 'pending' rows retryable — all three guards/wiring
        # must exist or a fault strands or refunds rows.
        wsrc = (root / "bridge_withdraw_monitor.py").read_text()
        assert wsrc.count("except ReserveUnknownError") >= 3
        assert "await _drain_pending_releases()" in wsrc


class TestPendingReleaseDrain:
    """#3072: a reserve fault (or a crash) leaves priced rows 'pending'
    with no re-drive — they would sit forever inflating the reserve.
    The drain retries them; an unknown reserve aborts the pass closed."""

    @pytest.mark.asyncio
    async def test_unknown_reserve_aborts_drain_without_refund(self, tmp_path, monkeypatch):
        bridge = _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)
        _withdrawal(bridge)  # insert_withdrawal defaults to status='pending'

        resolver_calls = []

        async def fake_resolve(*args, **kwargs):
            resolver_calls.append(args)

        released = []

        async def fake_release(*args, **kwargs):
            released.append((args, kwargs))
            raise wdm.ReserveUnknownError("term 'x' unreadable")

        monkeypatch.setattr(wdm, "_resolve_release_failure", fake_resolve)
        monkeypatch.setattr(wdm, "_release_eth_for_withdrawal", fake_release)

        out = await wdm._drain_pending_releases()
        assert out == {"released": 0, "still_waiting": 1}
        assert released and resolver_calls == []
        # The row is still 'pending' — retried next poll, never refunded.
        row = bridge_db.get_withdrawal_by_ait_tx_hash("0x" + "11" * 32)
        assert row["status"] == "pending"

    @pytest.mark.asyncio
    async def test_drain_releases_pending_row_once_reserve_heals(self, tmp_path, monkeypatch):
        bridge = _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)
        _withdrawal(bridge)

        released = []

        async def fake_release(withdrawal_id, ait_tx_hash, eth_address, amount_eth, **kwargs):
            released.append((withdrawal_id, ait_tx_hash, eth_address, amount_eth, kwargs))
            return "0x" + "ab" * 32

        monkeypatch.setattr(wdm, "_release_eth_for_withdrawal", fake_release)
        out = await wdm._drain_pending_releases()
        assert out == {"released": 1, "still_waiting": 0}
        assert released[0][3] == Decimal("0.2")
        assert released[0][4]["expected_statuses"] == {"pending"}

    def test_getter_returns_only_pending_rows(self, tmp_path, monkeypatch):
        from wallet_app.bridge.bridge_db import get_pending_release_withdrawals

        bridge = _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)
        _withdrawal(bridge)
        rows = get_pending_release_withdrawals()
        assert [r["ait_tx_hash"] for r in rows] == ["0x" + "11" * 32]
        assert rows[0]["status"] == "pending"
        assert rows[0]["amount_eth"] == Decimal("0.2")


class TestPriceRecordReserveGuard:
    """#3072: _price_record_and_release must let ReserveUnknownError
    propagate past the _OPS_ERRORS handler — that handler routes into
    _resolve_release_failure, whose 'not_sent' verdict refunds the AIT
    for what is only a temporary store fault."""

    @pytest.mark.asyncio
    async def test_reserve_unknown_propagates_without_refund_resolution(self, tmp_path, monkeypatch):
        _bridge_db(tmp_path, monkeypatch)
        _no_exchange_db(tmp_path, monkeypatch)

        async def fake_price(gross_ait):
            return {"amount_eth": Decimal("0.2"), "fee_ait": Decimal("0.01"), "net_ait": Decimal("9.9")}

        async def fake_release(*args, **kwargs):
            raise wdm.ReserveUnknownError("term 'withdrawals' unreadable")

        resolver_calls = []

        async def fake_resolve(*args, **kwargs):
            resolver_calls.append(args)

        monkeypatch.setattr(wdm, "calculate_eth_amount", fake_price)
        monkeypatch.setattr(wdm, "_release_eth_for_withdrawal", fake_release)
        monkeypatch.setattr(wdm, "_resolve_release_failure", fake_resolve)

        with pytest.raises(wdm.ReserveUnknownError):
            await wdm._price_record_and_release(
                ait_tx_hash="0x" + "44" * 32,
                sender="0x" + "55" * 20,
                eth_address="0x" + "66" * 20,
                gross_ait=Decimal("10"),
                block_height=100,
                block_hash="0x" + "77" * 32,
            )
        assert resolver_calls == []
        row = bridge_db.get_withdrawal_by_ait_tx_hash("0x" + "44" * 32)
        assert row["status"] == "pending"
