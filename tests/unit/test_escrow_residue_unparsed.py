"""ESCROW-RESIDUE-UNPARSEABLE-TERMINAL-AT-UNCOUNTED-1 — a residue whose
terminal_at does not parse must appear on its own gauge, never dropped."""

import importlib.util
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "escrow_residue_textfile", REPO / "scripts" / "monitoring" / "escrow-residue-textfile.py"
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

NOW = 1_700_000_000


def _db(tmp_path):
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE escrow (job_id TEXT, amount INTEGER, released_amount INTEGER, "
        "refunded_amount INTEGER, created_at TEXT, released_at TEXT, refunded_at TEXT, status TEXT)"
    )
    con.execute("CREATE TABLE escrow_leg (job_id TEXT, kind TEXT, tx_hash TEXT, amount INTEGER, confirmed_at TEXT)")
    # residue > 0, terminal state, terminal_at unparseable
    con.execute("INSERT INTO escrow VALUES ('bad-ts', 100, 0, 0, 'garbage', NULL, NULL, 'released')")
    con.commit()
    con.close()
    return str(db)


def test_unparseable_terminal_at_is_counted(tmp_path):
    rows = exporter.read_db(_db(tmp_path), NOW, 604800, 0, 0)
    assert rows is not None
    residues, unparsed = rows
    assert unparsed == 1
    text = exporter.render({"/db/chain.db": rows}, NOW)
    assert 'aitbc_escrow_residue_unparsed_total{db="/db/chain.db"} 1' in text
