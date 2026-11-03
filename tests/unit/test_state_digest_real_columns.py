"""STATE-DIGEST-REAL-COLUMNS-COLLAPSE-1 — datetime normalization must not
run on numeric columns: two DBs differing at 1e-10 must digest differently
while T/space datetime spellings still compare equal."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "state-digest-remote.py"

SPEC = json.dumps({"volatile": [], "addr_cols": [], "tables": {"liquidity_pool": {"class": "x"}}})


def _digest(db: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(db), "bc-2", SPEC],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def _mk(path: Path, share: float, ts: str) -> None:
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE "block" (height INTEGER, chain_id TEXT)')
    con.execute("INSERT INTO \"block\" VALUES (1,'bc-2')")
    con.execute("CREATE TABLE liquidity_pool (reward_per_share REAL, updated TEXT)")
    con.execute("INSERT INTO liquidity_pool VALUES (?,?)", (share, ts))
    con.commit()
    con.close()


def test_real_column_divergence_changes_digest(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    _mk(a, 0.5, "2026-01-01 12:00:00")
    _mk(b, 0.5000000001, "2026-01-01 12:00:00")
    assert _digest(a) != _digest(b)


def test_datetime_spelling_still_compares_equal(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    _mk(a, 0.5, "2026-01-01T12:00:00")
    _mk(b, 0.5, "2026-01-01 12:00:00")
    assert _digest(a) == _digest(b)
