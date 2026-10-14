"""Storage-layer CRUD tests for bridge-monitor's deposit table."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bridge_monitor import storage  # noqa: E402
from bridge_monitor.storage import BridgeDepositStatus  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "deposits.db"))
    storage.init_db()
    return storage


def test_create_get_deposit(db) -> None:
    dep_id = db.create_deposit("0xhash1", "0xfrom", "100", "ait1recipient")
    assert dep_id is not None

    row = db.get_deposit("0xhash1")
    assert row is not None
    assert row["eth_tx_hash"] == "0xhash1"
    assert row["status"] == BridgeDepositStatus.PENDING.value


def test_duplicate_tx_hash_returns_none(db) -> None:
    assert db.create_deposit("0xhash1", "0xfrom", "100", "ait1r") is not None
    assert db.create_deposit("0xhash1", "0xfrom", "100", "ait1r") is None


def test_update_deposit_status(db) -> None:
    db.create_deposit("0xhash2", "0xfrom", "50", "ait1r")
    db.update_deposit("0xhash2", status=BridgeDepositStatus.COMPLETED)

    row = db.get_deposit("0xhash2")
    assert row["status"] == "completed"


def test_list_and_count_filter_by_status(db) -> None:
    db.create_deposit("0xa", "0xf", "1", "r1")
    db.create_deposit("0xb", "0xf", "2", "r2")
    db.update_deposit("0xa", status=BridgeDepositStatus.FAILED)

    assert db.count_deposits() == 2
    assert db.count_deposits(BridgeDepositStatus.FAILED) == 1
    assert db.count_deposits(BridgeDepositStatus.PENDING) == 1
    assert [d["eth_tx_hash"] for d in db.get_deposits(BridgeDepositStatus.PENDING)] == ["0xb"]


def test_get_unknown_deposit_returns_none(db) -> None:
    assert db.get_deposit("0xnonexistent") is None


def test_create_deposit_records_deposit_address(db) -> None:
    """B13: the watched wallet is stored on the row for the reconcile."""
    db.create_deposit("0xhash9", "0xfrom", "100", "ait1r", deposit_address="0x310dcE00270D0aC10CAccfBD636Ff07BD5648781")
    row = db.get_deposit("0xhash9")
    assert row["deposit_address"] == "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"


def test_create_deposit_address_defaults_null(db) -> None:
    db.create_deposit("0xhash8", "0xfrom", "100", "ait1r")
    assert db.get_deposit("0xhash8")["deposit_address"] is None


def test_init_db_migrates_pre_b13_schema(tmp_path, monkeypatch) -> None:
    """A ledger predating the column migrates forward; existing rows keep
    NULL and init_db is idempotent."""
    import sqlite3

    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "old.db"))
    con = sqlite3.connect(tmp_path / "old.db")
    con.execute(
        "CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, tx_hash TEXT UNIQUE NOT NULL, "
        "from_address TEXT NOT NULL, amount_eth NUMERIC NOT NULL, amount_ait NUMERIC NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'pending')"
    )
    con.execute("INSERT INTO eth_deposits VALUES ('d0','0x01','0xabc','0.05','0','completed')")
    con.commit()
    con.close()

    storage.init_db()
    storage.init_db()  # idempotent

    con = sqlite3.connect(tmp_path / "old.db")
    columns = {row[1] for row in con.execute("PRAGMA table_info(eth_deposits)")}
    (addr,) = con.execute("SELECT deposit_address FROM eth_deposits WHERE id = 'd0'").fetchone()
    con.close()
    assert "deposit_address" in columns
    assert addr is None
