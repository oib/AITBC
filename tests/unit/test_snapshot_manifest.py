"""Tests for scripts/ops/snapshot-manifest.py (V-5 attested-snapshot manifest).

Fixtures are tiny chain.db files carrying the columns the tool selects:
``block`` (chain_id, height, hash, state_root) plus one apply-written table.
The manifest must be a pure function of the database: same bytes → same
manifest; one changed cell → different digest; a changed head → different
manifest.
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "snapshot-manifest.py"
CHAIN = "ait-test"


def _load():
    spec = importlib.util.spec_from_file_location("snapshot_manifest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["snapshot_manifest"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _mk_db(path: Path, *, head_hash: str = "0xdead", bond_amount: int = 100) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT,
                            state_root TEXT);
        CREATE TABLE bond (chain_id TEXT, address TEXT, amount INTEGER,
                           created_at TEXT);
        CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER,
                              nonce INTEGER);
        CREATE TABLE escrow (job_id TEXT, amount INTEGER);
        """
    )
    conn.execute("INSERT INTO block VALUES (?, ?, ?, ?)", (CHAIN, 7, head_hash, "0xroot"))
    conn.execute("INSERT INTO bond VALUES (?, ?, ?, ?)", (CHAIN, "addr1", bond_amount, "ts"))
    conn.commit()
    conn.close()
    return path


def _manifest(tool, db, **kw):
    conn = tool.connect_ro(str(db))
    m = tool.build_manifest(conn, str(db), CHAIN, with_state_root=False)
    conn.close()
    return m


def test_manifest_is_deterministic(tool, tmp_path):
    db = _mk_db(tmp_path / "a.db")
    m1 = _manifest(tool, db)
    m2 = _manifest(tool, db)
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)


def test_changed_row_changes_digest(tool, tmp_path):
    db1 = _mk_db(tmp_path / "a.db", bond_amount=100)
    db2 = _mk_db(tmp_path / "b.db", bond_amount=101)
    m1, m2 = _manifest(tool, db1), _manifest(tool, db2)
    assert m1["table_digests"]["candidates"]["bond"]["digest"] != m2["table_digests"]["candidates"]["bond"]["digest"]


def test_changed_head_changes_manifest(tool, tmp_path):
    db1 = _mk_db(tmp_path / "a.db", head_hash="0xdead")
    db2 = _mk_db(tmp_path / "b.db", head_hash="0xbeef")
    m1, m2 = _manifest(tool, db1), _manifest(tool, db2)
    assert m1 != m2 and m1["head"]["hash"] != m2["head"]["hash"]


def test_manifest_shape(tool, tmp_path):
    m = _manifest(tool, _mk_db(tmp_path / "a.db"))
    assert m["format"] == tool.MANIFEST_FORMAT
    assert m["chain_id"] == CHAIN
    assert m["head"] == {"height": 7, "hash": "0xdead"}
    assert m["signature"] == ""  # clearly named, empty — signing is separate
    assert "signature_note" in m
    assert m["state_root"]["skipped"] is True
    assert m["row_counts"]["block"] == 1 and m["row_counts"]["bond"] == 1
    assert "candidates" in m["table_digests"] and "controls" in m["table_digests"]


def test_state_root_recompute_against_fixture(tool, tmp_path):
    """With aitbc_chain importable the recompute runs over a read-only
    session; the fixture's recorded root deliberately differs."""
    pytest.importorskip("aitbc_chain.state.state_root_utils")
    db = _mk_db(tmp_path / "a.db")
    conn = tool.connect_ro(str(db))
    m = tool.build_manifest(conn, str(db), CHAIN, with_state_root=True)
    conn.close()
    # No account rows → root is the empty-trie root; recorded "0xroot" differs.
    assert m["state_root"]["recomputed"] is not None
    assert m["state_root"]["match"] is False


def test_connect_ro_honors_wal(tool, tmp_path):
    """Plain mode=ro (not immutable=1) must see rows living only in the WAL —
    a live node's newest commits sit there uncheckpointed."""
    db = tmp_path / "wal.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.executescript("CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, state_root TEXT);")
    writer.execute("INSERT INTO block VALUES (?, ?, ?, ?)", (CHAIN, 9, "hwal", "0xr"))
    writer.commit()
    try:
        assert (tmp_path / "wal.db-wal").exists(), "fixture must hold uncheckpointed WAL pages"
        conn = tool.connect_ro(str(db))
        assert conn.execute("SELECT COUNT(*) FROM block").fetchone()[0] == 1
        conn.close()
    finally:
        writer.close()


def test_connection_is_query_only(tool, tmp_path):
    db = _mk_db(tmp_path / "a.db")
    conn = tool.connect_ro(str(db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO block VALUES ('x', 1, 'h', 'r')")
    conn.close()


def test_ambiguous_chain_requires_flag(tool, tmp_path):
    db = tmp_path / "multi.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, state_root TEXT);"
        "INSERT INTO block VALUES ('a', 1, 'h1', 'r'), ('b', 1, 'h2', 'r');"
    )
    conn.commit()
    conn.close()
    assert tool.main(["--db", str(db)]) == 2
    assert tool.main(["--db", str(db), "--chain-id", "a"]) == 0
