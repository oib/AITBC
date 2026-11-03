"""BRIDGE-SET-TEXTFILE-PARTIAL-READ-HIDDEN-1 — a skipped chain.db must
surface: scrape_success 0, a stderr line naming it, exit 1."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "bridge-set-textfile.py"


def _env(tmp_path: Path) -> dict:
    tf = tmp_path / "prom"
    tf.mkdir()
    return {
        "AITBC_DATA_DIR": str(tmp_path),
        "AITBC_TEXTFILE_DIR": str(tf),
        "VALIDATOR_SET": "[]",
        "PATH": "/usr/bin:/bin",
    }


def _mk_chain(root: Path, chain: str, good: bool) -> None:
    d = root / "data" / chain
    d.mkdir(parents=True)
    con = sqlite3.connect(d / "chain.db")
    if good:
        con.execute("CREATE TABLE bridge_validator (address TEXT)")
        con.execute("INSERT INTO bridge_validator VALUES ('0x1')")
    else:
        con.execute("CREATE TABLE other (x TEXT)")
    con.commit()
    con.close()


def test_broken_db_fails_the_scrape(tmp_path):
    _mk_chain(tmp_path, "bc-2", good=True)
    _mk_chain(tmp_path, "bc-3", good=False)
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env={**os.environ, **_env(tmp_path)},
    )
    assert r.returncode == 1
    assert "bc-3" in r.stderr
    prom = (tmp_path / "prom" / "aitbc_bridge_set.prom").read_text()
    assert "aitbc_bridge_set_scrape_success 0" in prom
