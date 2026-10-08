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


def test_output_prints_no_row_data(tool, tmp_path, capsys):
    db = _mk_db(tmp_path / "a.db", ROWS_A)
    assert tool.main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "addr1" not in out and "addr2" not in out
    assert "bond" in out and "digest=" in out
    assert "candidate fingerprint:" in out
