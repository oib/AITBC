"""Tests for scripts/ops/side-root-probe.py (V-3 first step).

Each test builds a small chain.db fixture in a temp dir with just the columns
the tool selects, and exercises the digest invariants a fleet run relies on:
identical logical content must give identical digests regardless of insert
order, a single changed cell must change the digest, and locally-stamped
volatile columns must not leak divergence into it.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "side-root-probe.py"


def _load():
    spec = importlib.util.spec_from_file_location("side_root_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["side_root_probe"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _mk_db(path: Path, rows: list[tuple], *, extra_col: bool = False) -> Path:
    conn = sqlite3.connect(path)
    extra = ", status TEXT" if extra_col else ""
    conn.executescript(
        f"""
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT);
        CREATE TABLE bond (chain_id TEXT, address TEXT, amount INTEGER, created_at TEXT{extra});
        CREATE TABLE escrow (job_id TEXT, amount INTEGER);
        INSERT INTO block VALUES ('ait-test', 7, 'h7');
        """
    )
    for r in rows:
        if extra_col:
            conn.execute("INSERT INTO bond VALUES (?, ?, ?, ?, 'x')", (*r, "stamp-a"))
        else:
            conn.execute("INSERT INTO bond VALUES (?, ?, ?, ?)", (*r, "stamp-a"))
    conn.commit()
    conn.close()
    return path


ROWS_A = [("ait-test", "addr1", 100), ("ait-test", "addr2", 200)]


def test_identical_contents_identical_digest(tool, tmp_path):
    db1 = _mk_db(tmp_path / "a.db", ROWS_A)
    db2 = _mk_db(tmp_path / "b.db", list(reversed(ROWS_A)))
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "bond")
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "bond")
    assert d1["rows"] == 2 and d1["digest"] == d2["digest"]


def test_one_changed_cell_changes_digest(tool, tmp_path):
    db1 = _mk_db(tmp_path / "a.db", ROWS_A)
    db2 = _mk_db(tmp_path / "b.db", [("ait-test", "addr1", 100), ("ait-test", "addr2", 201)])
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "bond")
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "bond")
    assert d1["digest"] != d2["digest"]


def test_volatile_column_does_not_diverge(tool, tmp_path):
    """created_at stamped differently per host must not change the digest."""
    db1 = _mk_db(tmp_path / "a.db", ROWS_A)
    db2 = _mk_db(tmp_path / "b.db", ROWS_A)
    conn = sqlite3.connect(db2)
    conn.execute("UPDATE bond SET created_at = 'stamp-b'")
    conn.commit()
    conn.close()
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "bond")
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "bond")
    assert d1["digest"] == d2["digest"]
    assert d1["skipped_cols"] == ["created_at"]


def test_schema_drift_changes_digest(tool, tmp_path):
    """A different non-volatile column list must not collide with the same
    cell values (volatile columns are excluded by design — tested above)."""
    db1 = _mk_db(tmp_path / "a.db", ROWS_A)
    db2 = _mk_db(tmp_path / "b.db", ROWS_A, extra_col=True)
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "bond")
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "bond")
    assert d1["digest"] != d2["digest"]


def test_absent_table(tool, tmp_path):
    db = _mk_db(tmp_path / "a.db", ROWS_A)
    entry = tool.table_digest(tool.connect_ro(str(db)), "chain_parameter")
    assert entry == {"status": "absent"}


def test_connection_is_query_only(tool, tmp_path):
    """Read-only by construction: the kernel refuses a write on the probe's
    own connection — there is no write path to hide."""
    db = _mk_db(tmp_path / "a.db", ROWS_A)
    conn = tool.connect_ro(str(db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO bond VALUES ('x', 'y', 1, 'z')")
    conn.close()


def test_wal_contents_visible(tool, tmp_path):
    """Plain mode=ro must honor the WAL: a live node holds its newest commits
    in chain.db-wal and immutable=1 would skip them. Keep a WAL writer open
    (no checkpoint) and prove the probe sees the uncheckpointed row."""
    db = tmp_path / "wal.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT);
        CREATE TABLE bond (chain_id TEXT, address TEXT, amount INTEGER, created_at TEXT);
        INSERT INTO block VALUES ('ait-test', 7, 'h7');
        """
    )
    writer.execute("INSERT INTO bond VALUES ('ait-test', 'addr1', 100, 'stamp')")
    writer.commit()
    try:
        assert (tmp_path / "wal.db-wal").exists(), "fixture must hold uncheckpointed WAL pages"
        conn = tool.connect_ro(str(db))
        entry = tool.table_digest(conn, "bond")
        conn.close()
        assert entry["rows"] == 1  # the WAL row — invisible under immutable=1
    finally:
        writer.close()


def test_output_prints_no_row_data(tool, tmp_path, capsys):
    db = _mk_db(tmp_path / "a.db", ROWS_A)
    assert tool.main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "addr1" not in out and "addr2" not in out
    assert "bond" in out and "digest=" in out
    assert "candidate fingerprint:" in out


# --- V-3 activation-rule fixtures (--canonical) -------------------------------


def _mk_dual_writer_db(path: Path, *, address: str, registered_at: str, locked_until: str | None = None) -> Path:
    """Fixture shaped like the dual-writer tables: 0x address columns plus
    locally-stamped *_at timestamps."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT);
        CREATE TABLE gpu_registration (
            id INTEGER PRIMARY KEY, chain_id TEXT, gpu_id TEXT, miner_id TEXT,
            registered_by TEXT, registered_at TEXT, status TEXT, updated_at TEXT
        );
        CREATE TABLE stake (
            id INTEGER PRIMARY KEY, chain_id TEXT, address TEXT, amount INTEGER,
            locked_until TEXT, created_at TEXT, updated_at TEXT, status TEXT
        );
        INSERT INTO block VALUES ('ait-test', 7, 'h7');
        """
    )
    conn.execute(
        "INSERT INTO gpu_registration VALUES (1, 'ait-test', 'gpu1', ?, ?, ?, 'active', 'u1')",
        (address, address, registered_at),
    )
    conn.execute(
        "INSERT INTO stake VALUES (1, 'ait-test', ?, 100, ?, 'c1', 'u1', 'locked')",
        (address, locked_until),
    )
    conn.commit()
    conn.close()
    return path


ADDR_LOWER = "0xaabbccddee0011223344556677889900aabbcc"
ADDR_MIXED = "0xaabbccDDEE0011223344556677889900AABBcc"


def test_canonical_address_case_ignored(tool, tmp_path):
    """Hub stores stake.address checksummed, followers lowercase — under the
    activation rules the encodings are the same logical value."""
    db1 = _mk_dual_writer_db(tmp_path / "a.db", address=ADDR_LOWER, registered_at="t1")
    db2 = _mk_dual_writer_db(tmp_path / "b.db", address=ADDR_MIXED, registered_at="t1")
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "stake", canonical=True)
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "stake", canonical=True)
    assert d1["digest"] == d2["digest"]
    # …and raw mode still sees the divergence — canonical is opt-in.
    r1 = tool.table_digest(tool.connect_ro(str(db1)), "stake")
    r2 = tool.table_digest(tool.connect_ro(str(db2)), "stake")
    assert r1["digest"] != r2["digest"]


def test_canonical_star_at_columns_excluded(tool, tmp_path):
    """registered_at/allocated_at/completed_at diverge legitimately per host;
    the *_at rule must exclude them all, not just created_at/updated_at."""
    db1 = _mk_dual_writer_db(tmp_path / "a.db", address=ADDR_LOWER, registered_at="2026-01-01")
    db2 = _mk_dual_writer_db(tmp_path / "b.db", address=ADDR_LOWER, registered_at="2026-10-08")
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "gpu_registration", canonical=True)
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "gpu_registration", canonical=True)
    assert d1["digest"] == d2["digest"]
    assert "registered_at" in d1["skipped_cols"] and "updated_at" in d1["skipped_cols"]


def test_canonical_real_divergence_still_detected(tool, tmp_path):
    """Canonicalization is not a blanket suppressor: a semantically different
    row (different amount) must still diverge."""
    db1 = _mk_dual_writer_db(tmp_path / "a.db", address=ADDR_LOWER, registered_at="t1")
    db2 = _mk_dual_writer_db(tmp_path / "b.db", address=ADDR_LOWER, registered_at="t1")
    conn = sqlite3.connect(db2)
    conn.execute("UPDATE stake SET amount = 200")
    conn.commit()
    conn.close()
    d1 = tool.table_digest(tool.connect_ro(str(db1)), "stake", canonical=True)
    d2 = tool.table_digest(tool.connect_ro(str(db2)), "stake", canonical=True)
    assert d1["digest"] != d2["digest"]


def test_canonical_collect_partitions_sets(tool, tmp_path):
    """--canonical partitions candidates into committed set (10 tables) and
    the 3 probationary dual-writer tables; fingerprint covers committed only."""
    db = _mk_dual_writer_db(tmp_path / "a.db", address=ADDR_LOWER, registered_at="t1")
    conn = tool.connect_ro(str(db))
    result = tool.collect(conn, canonical=True)
    conn.close()
    assert set(result["committed_set"]) == set(tool.RESTRICTED_TABLES)
    assert set(result["canonicalized"]) == set(tool.CANONICALIZED_TABLES)
    assert not result["candidates"]
    assert result["canonicalized"]["stake"]["digest"]
    assert "candidate fingerprint" not in result or result["candidate_fingerprint"]


def test_canonical_sets_cover_candidates(tool):
    """The classification must be exhaustive: every apply-written candidate
    lands in exactly one set, so a new table cannot be silently half-committed."""
    assert set(tool.RESTRICTED_TABLES).isdisjoint(tool.CANONICALIZED_TABLES)
    assert set(tool.RESTRICTED_TABLES) | set(tool.CANONICALIZED_TABLES) == set(tool.CANDIDATE_TABLES)
