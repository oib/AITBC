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


def test_db_path_env_precedence(tmp_path, monkeypatch):
    """AITBC_DATA_DIR wins over the operator-facing DATA_DIR override.

    DATA_DIR/DB_PATH bind at import, so re-derive via reload and restore
    afterwards — a dirty module constant would leak into later tests.
    """
    import importlib

    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path / "ns"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "bare"))
    try:
        importlib.reload(storage)
        assert storage.DATA_DIR == str(tmp_path / "ns")
        assert storage.DB_PATH == os.path.join(str(tmp_path / "ns"), "data", "bridge_deposits.db")
        monkeypatch.delenv("AITBC_DATA_DIR")
        importlib.reload(storage)
        assert storage.DATA_DIR == str(tmp_path / "bare")
        assert storage.DB_PATH == os.path.join(str(tmp_path / "bare"), "data", "bridge_deposits.db")
    finally:
        monkeypatch.undo()
        importlib.reload(storage)


def test_release_sources_normalizes_prefixes(db, tmp_path) -> None:
    """Unprefixed web3 tx.hash.hex() must join 0x-prefixed release rows (#652)."""
    import sqlite3

    # release-leg tables live beside the deposits db
    con = sqlite3.connect(tmp_path / "deposits.db")
    con.execute("CREATE TABLE eth_withdrawals (eth_tx_hash TEXT)")
    con.execute("INSERT INTO eth_withdrawals VALUES ('0xAbC123'), ('deadbeef')")
    con.commit()
    con.close()

    sources = db.release_sources()
    assert sources["0xabc123"] == "" or "0xabc123" in sources
    assert db.canon_tx_hash("abc123") == "0xabc123"
    assert db.canon_tx_hash("0xAbC123") == "0xabc123"
    assert db.canon_tx_hash("deadbeef") == "0xdeadbeef"
    assert "0xdeadbeef" in sources  # unprefixed row also canonicalized


def test_deposit_tx_hash_canonicalized_on_write(db) -> None:
    """The two deposit writers spell one hash differently — web3's bare
    ``tx.hash.hex()`` vs the wallet's ``0x``-prefixed RPC hash. Both must
    land on one canonical key or the UNIQUE dedupe lets the same ETH
    deposit pay out twice (issue #668)."""
    assert db.create_deposit("deadbeef01", "0xfrom", "100", "ait1r") is not None
    # Same deposit via the other spelling must dedupe, not double-insert.
    assert db.create_deposit("0xDeadBeef01", "0xfrom", "100", "ait1r") is None

    row = db.get_deposit("0xdeadbeef01")
    assert row is not None
    assert row["eth_tx_hash"] == "0xdeadbeef01"


def test_get_deposit_matches_any_spelling(db, tmp_path) -> None:
    """Legacy rows (bare or mixed-case) and lookups stay reachable."""
    import sqlite3

    con = sqlite3.connect(tmp_path / "deposits.db")
    con.execute(
        "INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, amount_ait, status) "
        "VALUES ('legacy-bare', 'cafe01', '0xf', '1', '0', 'pending'), "
        "('legacy-mixed', '0xAbC02', '0xf', '1', '0', 'pending')"
    )
    con.commit()
    con.close()

    for spelling in ("cafe01", "0xcafe01", "0xCAFE01"):
        assert db.get_deposit(spelling)["id"] == "legacy-bare"
    for spelling in ("abc02", "0xabc02", "0xABC02"):
        assert db.get_deposit(spelling)["id"] == "legacy-mixed"


def test_update_deposit_matches_any_spelling(db, tmp_path) -> None:
    """An update keyed by the web3-bare spelling must reach a row written
    ``0x``-prefixed (and vice versa) — otherwise lifecycle updates silently
    miss and the deposit re-enters the payout path (issue #668)."""
    import sqlite3

    con = sqlite3.connect(tmp_path / "deposits.db")
    con.execute(
        "INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, amount_ait, status) "
        "VALUES ('d-mixed', '0xF00D03', '0xf', '1', '0', 'pending')"
    )
    con.commit()
    con.close()

    db.update_deposit("f00d03", status=BridgeDepositStatus.COMPLETED)
    assert db.get_deposit("0xf00d03")["status"] == "completed"


def test_canon_tx_hash_passes_nonhex_ids_through(db) -> None:
    """Synthetic ids (``manual-…`` payout rows) are not tx hashes."""
    assert db.canon_tx_hash("manual-20260101T000000") == "manual-20260101T000000"
    assert db.get_deposit("manual-20260101T000000") is None  # no crash on non-hex


def test_record_outbound_canonicalizes_tx_hash(db, tmp_path) -> None:
    """A re-scan spelling the same leg differently must dedupe on the
    PRIMARY KEY, not double-ledger the outbound leg (issue #668)."""
    assert db.record_outbound("beef04", "0xto", 10**18, 7, "unidentified") is True
    assert db.record_outbound("0xBEEF04", "0xto", 10**18, 7, "unidentified") is False

    import sqlite3

    con = sqlite3.connect(tmp_path / "deposits.db")
    (stored,) = con.execute("SELECT tx_hash FROM bridge_outbound").fetchone()
    con.close()
    assert stored == "0xbeef04"
