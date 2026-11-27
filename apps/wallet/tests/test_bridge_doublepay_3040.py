"""#3040 AUDIT-BRIDGE-DEPOSIT-DOUBLE-PAY-1 pins — wallet side of the fix.

``eth_deposits`` is shared with aitbc-bridge-monitor, which scans the
same Ethereum address. This service's rows are stamped ``owner='wallet'``
so the monitor's adoption gate can prove it did NOT create them, and a
mint failure AFTER ``_submit_transfer`` returns a chain hash must park
the row at 'failed' — never re-pend it into vocabulary another watcher
can pick up (the deterministic double-pay: wallet TRANSFER seals AND the
monitor pays the same deposit again).
"""

from __future__ import annotations

import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _NonceClient:
    @staticmethod
    async def get(url, **kwargs):
        return _Resp({"nonce": 0})


class _PostClient:
    """Fake httpx.AsyncClient: __aenter__ returns self, post() is scripted."""

    outcome: object = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        outcome = type(self).outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _arm_db(monkeypatch, tmp_path: Path):
    """Fresh wallet bridge DB on a scratch path; returns (bridge_db, path)."""
    from wallet_app.bridge import bridge_db

    db_path = tmp_path / "bridge.db"
    monkeypatch.setattr(bridge_db, "DB_PATH", str(db_path))
    bridge_db.init_db()
    return bridge_db, db_path


def _owner_of(db_path: Path, row_id: str) -> str | None:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT owner FROM eth_deposits WHERE id = ?", (row_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


class TestOwnershipStamp:
    def test_insert_deposit_stamps_wallet_owner(self, tmp_path, monkeypatch):
        bridge_db, db_path = _arm_db(monkeypatch, tmp_path)
        deposit_id = bridge_db.insert_deposit(
            "0x" + "a1" * 32, "0xfrom", Decimal("1"), Decimal("100"), recipient="0x" + "d" * 40
        )
        assert _owner_of(db_path, deposit_id) == "wallet"

    def test_insert_exchange_prepay_stamps_wallet_owner(self, tmp_path, monkeypatch):
        bridge_db, db_path = _arm_db(monkeypatch, tmp_path)
        deposit_id = bridge_db.insert_exchange_prepay_deposit("0x" + "b2" * 32, "0xfrom", Decimal("1"), "0xtag")
        assert _owner_of(db_path, deposit_id) == "wallet"

    def test_owner_column_added_by_migration(self, tmp_path, monkeypatch):
        """A pre-column DB migrates forward: owner added, existing rows
        keep NULL (ambiguous — the monitor refuses to adopt their
        'pending' state rather than guess)."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, tx_hash TEXT UNIQUE NOT NULL, "
            "from_address TEXT NOT NULL, amount_eth NUMERIC NOT NULL, amount_ait NUMERIC NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'pending')"
        )
        conn.execute("INSERT INTO eth_deposits VALUES ('d0','0x01','0xabc','0.05','0','pending')")
        conn.commit()
        conn.close()

        from wallet_app.bridge import bridge_db

        monkeypatch.setattr(bridge_db, "DB_PATH", str(db_path))
        bridge_db.init_db()
        bridge_db.init_db()  # idempotent

        conn = sqlite3.connect(db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(eth_deposits)")}
        (owner,) = conn.execute("SELECT owner FROM eth_deposits WHERE id = 'd0'").fetchone()
        conn.close()
        assert "owner" in columns
        assert owner is None


class TestPendingVocabulary:
    def test_get_pending_deposits_hides_monitor_owned_rows(self, tmp_path, monkeypatch):
        """A monitor-created 'pending' crash remnant is not the wallet's
        to mint — the pending vocabulary excludes owner='monitor'."""
        bridge_db, db_path = _arm_db(monkeypatch, tmp_path)
        wallet_id = bridge_db.insert_deposit("0x" + "c3" * 32, "0xfrom", Decimal("1"), Decimal("100"))
        # Monitor-side row, same shape create_deposit writes.
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, amount_ait, status, created_at, owner) "
            "VALUES ('deposit_mon','0xmon','0xfrom','1','100','pending','2026-01-01','monitor')"
        )
        # Legacy ambiguous row — stays listed (unclaimed, operator-visible).
        conn.execute(
            "INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, amount_ait, status, created_at) "
            "VALUES ('deposit_leg','0xleg','0xfrom','1','100','pending','2026-01-01')"
        )
        conn.commit()
        conn.close()

        pending_ids = {d["id"] for d in bridge_db.get_pending_deposits()}
        assert wallet_id in pending_ids
        assert "deposit_leg" in pending_ids
        assert "deposit_mon" not in pending_ids


def _arm_mint(monkeypatch, tmp_path: Path, post_outcome):
    """_mint_deposit armed against a scratch DB; post() returns a chain hash."""
    from wallet_app.bridge import bridge_monitor as bm

    bridge_db, db_path = _arm_db(monkeypatch, tmp_path)
    recipient = "0x" + "d" * 40
    deposit_id = bridge_db.insert_deposit("0xeth3040", "0xfrom", Decimal("1"), Decimal("100"), recipient=recipient)

    monkeypatch.setattr(bm, "SharedHttpClient", _NonceClient)
    monkeypatch.setattr(bm, "GENESIS_WALLET_ADDRESS", "0x" + "b" * 40)
    monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0x" + "c" * 64)
    monkeypatch.setattr(bm, "BLOCKCHAIN_RPC_URL", "http://test-rpc")
    monkeypatch.setenv("CHAIN_ID", "test-chain")

    class Scripted(_PostClient):
        outcome = post_outcome

    monkeypatch.setattr(bm.httpx, "AsyncClient", Scripted)
    return bm, bridge_db, db_path, deposit_id, recipient


class TestPostSubmitNeverRePends:
    """Once _submit_transfer returns a chain hash the TRANSFER may already
    be broadcast — the completed/tx-hash CAS region must obey the same
    ambiguity rule as the submit path: park 'failed', never 'pending'."""

    @pytest.mark.asyncio
    async def test_completed_cas_sqlite_failure_parks_failed(self, tmp_path, monkeypatch):
        """The deterministic #3040 shape: 'database is locked' on the
        completed-CAS after broadcast. Unfixed code re-pends the row —
        which the monitor then adopts and pays a second time."""
        bm, bridge_db, _db_path, deposit_id, recipient = _arm_mint(
            monkeypatch, tmp_path, _Resp({"transaction_hash": "0xpaid3040"})
        )

        real_update = bm.update_deposit_status

        def locked_on_completed(deposit_id_arg, status, **kwargs):
            if status == "completed":
                raise sqlite3.OperationalError("database is locked")
            return real_update(deposit_id_arg, status, **kwargs)

        monkeypatch.setattr(bm, "update_deposit_status", locked_on_completed)

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        row = bridge_db.get_deposit_by_id(deposit_id)
        assert row["status"] == "failed"
        assert deposit_id not in {d["id"] for d in bridge_db.get_pending_deposits()}

    @pytest.mark.asyncio
    async def test_tx_hash_write_failure_keeps_completed(self, tmp_path, monkeypatch):
        """The completed CAS landed but the tx-hash write hit the lock —
        the row must stay 'completed' (paid marker kept), never 'failed'
        or 'pending'."""
        bm, bridge_db, _db_path, deposit_id, recipient = _arm_mint(
            monkeypatch, tmp_path, _Resp({"transaction_hash": "0xpaid3040"})
        )

        def locked_tx_hash(deposit_id_arg, ait_tx_hash, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(bm, "update_deposit_tx_hash", locked_tx_hash)

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        row = bridge_db.get_deposit_by_id(deposit_id)
        assert row["status"] == "completed"

    @pytest.mark.asyncio
    async def test_failed_park_write_failure_stays_verified(self, tmp_path, monkeypatch):
        """Even the 'failed' park write can hit the lock — the row then
        stays 'verified': still not re-mintable, still not adoptable by
        the monitor (WALLET_LIFECYCLE), visible to the stranded alert."""
        bm, bridge_db, _db_path, deposit_id, recipient = _arm_mint(
            monkeypatch, tmp_path, _Resp({"transaction_hash": "0xpaid3040"})
        )

        real_update = bm.update_deposit_status

        def locked_on_terminal(deposit_id_arg, status, **kwargs):
            if status in ("completed", "failed"):
                raise sqlite3.OperationalError("database is locked")
            return real_update(deposit_id_arg, status, **kwargs)

        monkeypatch.setattr(bm, "update_deposit_status", locked_on_terminal)

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        row = bridge_db.get_deposit_by_id(deposit_id)
        assert row["status"] == "verified"
        assert deposit_id not in {d["id"] for d in bridge_db.get_pending_deposits()}

    @pytest.mark.asyncio
    async def test_pre_submit_failure_still_re_pends(self, tmp_path, monkeypatch):
        """Guard against over-correction: a signing failure BEFORE any
        broadcast sent nothing — re-pending stays correct."""
        bm, bridge_db, _db_path, deposit_id, recipient = _arm_mint(
            monkeypatch, tmp_path, _Resp({"transaction_hash": "0xpaid3040"})
        )
        monkeypatch.setattr(bm, "GENESIS_WALLET_PRIVATE_KEY", "0xnot-hex")

        await bm._mint_deposit(deposit_id, recipient, Decimal("100"))

        row = bridge_db.get_deposit_by_id(deposit_id)
        assert row["status"] == "pending"


class TestCrossServiceSharedTable:
    """Both services' real code against ONE scratch DB file."""

    def _monitor_on(self, monkeypatch, db_path: Path):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "bridge-monitor" / "src"))
        from bridge_monitor import storage as monitor_storage
        from bridge_monitor.main import BridgeMonitor

        monkeypatch.setattr(monitor_storage, "DATA_DIR", str(db_path.parent))
        monkeypatch.setattr(monitor_storage, "DB_PATH", str(db_path))
        monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0x" + "a" * 40)
        monkeypatch.setenv("BRIDGE_PAYOUT_ADDRESS", "0x" + "b" * 40)
        monkeypatch.setenv("BRIDGE_PAYOUT_PRIVATE_KEY", "0x" + "c" * 64)
        monkeypatch.setenv("BRIDGE_MIN_DEPOSIT_AIT", "1")
        with patch("bridge_monitor.main.EthereumRPCClient"), patch("bridge_monitor.main.get_price_oracle"):
            return BridgeMonitor(), monitor_storage

    def test_wallet_pending_row_not_adopted_by_monitor(self, tmp_path, monkeypatch):
        """The raced #3040 sequence: the wallet watcher inserts a
        'pending' row and its mint is in flight; the monitor's scan sees
        the same tx and must refuse to adopt it."""
        bridge_db, db_path = _arm_db(monkeypatch, tmp_path)
        tx_hash = "0x" + "e5" * 32
        deposit_id = bridge_db.insert_deposit(tx_hash, "0xfrom", Decimal("1"), Decimal("100"), recipient="0x" + "d" * 40)

        monitor, monitor_storage = self._monitor_on(monkeypatch, db_path)

        seen = monitor_storage.get_deposit(tx_hash)
        assert seen is not None
        assert seen["owner"] == "wallet"
        assert seen["status"] == "pending"

        with (
            patch.object(monitor, "_submit_payout") as mock_submit,
            patch.object(monitor, "_build_signed_transfer") as mock_build,
            patch.object(monitor, "_post_signed_tx") as mock_post,
        ):
            monitor.process_deposit(tx_hash, "0xfrom", Decimal("1.0"), "0xdata")

        mock_submit.assert_not_called()
        mock_build.assert_not_called()
        mock_post.assert_not_called()
        row = bridge_db.get_deposit_by_tx_hash(tx_hash)
        assert row["status"] == "pending"
        assert row["id"] == deposit_id

    def test_monitor_row_invisible_to_wallet_pending_mint(self, tmp_path, monkeypatch):
        """Symmetric direction: a monitor-owned 'pending' row on the shared
        table is not wallet pending vocabulary."""
        bridge_db, db_path = _arm_db(monkeypatch, tmp_path)
        monitor, monitor_storage = self._monitor_on(monkeypatch, db_path)

        assert monitor_storage.create_deposit("0x" + "f6" * 32, "0xfrom", "1.0", "0x" + "d" * 40) is not None

        pending_tx = {d["tx_hash"] for d in bridge_db.get_pending_deposits()}
        assert "0x" + "f6" * 32 not in pending_tx
        # And the monitor side sees its own mark.
        row = monitor_storage.get_deposit("0x" + "f6" * 32)
        assert row["owner"] == "monitor"
