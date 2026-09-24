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
