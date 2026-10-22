"""MON-DB-GLOB-1 (#367): the five chain-db glob users skip zero-byte and
non-sqlite files with a log line; explicit pins keep strict failure; exit 1
logs a reason.

A probe artifact (a zero-byte or non-db file named chain.db / bridge_deposits*.db
next to the real one) must not turn a monitor run into a failure.
"""

from __future__ import annotations

import glob
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MON = REPO / "scripts" / "monitoring"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


arrival = _load("attestation_arrival_textfile", MON / "attestation-arrival-textfile.py")
residue = _load("escrow_residue_textfile", MON / "escrow-residue-textfile.py")
settlements = _load("escrow_settlements_textfile", MON / "escrow-settlements-textfile.py")
bridge_set = _load("bridge_set_textfile", MON / "bridge-set-textfile.py")
audit = _load("bridge_payout_audit", MON / "bridge-payout-audit.py")

FINDERS = [
    ("attestation-arrival", arrival),
    ("escrow-residue", residue),
    ("escrow-settlements", settlements),
]


def _mk_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """data/<chain>/chain.db layout: one real sqlite, one zero-byte, one text file."""
    good = tmp_path / "data" / "live" / "chain.db"
    good.parent.mkdir(parents=True)
    con = sqlite3.connect(good)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.close()
    empty = tmp_path / "data" / "stray" / "chain.db"
    empty.parent.mkdir(parents=True)
    empty.touch()
    text = tmp_path / "data" / "notdb" / "chain.db"
    text.parent.mkdir(parents=True)
    text.write_text("not a database")
    return good, empty, text


@pytest.mark.parametrize("label,mod", FINDERS)
def test_scan_skips_empty_and_non_sqlite(label, mod, tmp_path, capsys):
    good, empty, text = _mk_tree(tmp_path)
    found = mod.find_chain_dbs(str(tmp_path))
    assert found == [str(good)]
    err = capsys.readouterr().err
    assert f"{label}: skipping non-sqlite glob hit {empty}" in err
    assert f"{label}: skipping non-sqlite glob hit {text}" in err


def test_bridge_set_scan_skips_empty_and_non_sqlite(tmp_path, capsys):
    good, empty, text = _mk_tree(tmp_path)
    found = bridge_set.find_dbs(None, str(tmp_path))
    assert found == [str(good)]
    err = capsys.readouterr().err
    assert f"bridge-set: skipping non-sqlite glob hit {empty}" in err
    assert f"bridge-set: skipping non-sqlite glob hit {text}" in err


@pytest.mark.parametrize("label,mod", FINDERS)
def test_explicit_pin_stays_strict(label, mod, tmp_path, monkeypatch):
    _, empty, _ = _mk_tree(tmp_path)
    monkeypatch.setenv("AITBC_CHAIN_DB", str(empty))
    assert mod.resolve_dbs() == [str(empty)]  # returned unfiltered — failure stays strict


def test_bridge_set_explicit_pin_stays_strict(tmp_path):
    _, empty, _ = _mk_tree(tmp_path)
    assert bridge_set.find_dbs(str(empty), str(tmp_path)) == [str(empty)]


def test_arrival_exit1_logs_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))  # no chain.db at all
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))
    assert arrival.main() == 1
    assert "attestation-arrival: no chain.db found" in capsys.readouterr().err


def test_residue_exit1_logs_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))
    assert residue.main() == 1
    assert "escrow-residue: no chain.db found" in capsys.readouterr().err


def test_bridge_set_exit1_logs_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))
    monkeypatch.setenv("AITBC_CHAIN_DB", "")  # ensure scan path, not a stale pin
    assert bridge_set.main([]) == 1
    assert "bridge-set: no readable chain.db" in capsys.readouterr().err


def test_settlements_no_db_exit_logs_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))
    monkeypatch.setenv("AITBC_CHAIN_DB", "")
    assert settlements.main() == 2
    assert "escrow-settlements: no chain.db found" in capsys.readouterr().err


# --- bridge-payout-audit remote blobs ------------------------------------


def _fake_glob(good: Path, *strays: Path):
    """glob.glob returning the fixture files regardless of pattern."""

    def fake(pattern, **kw):
        return [str(p) for p in (good, *strays)]

    return fake


def test_ledger_blob_skips_non_sqlite(tmp_path, monkeypatch, capsys):
    good, empty, text = _mk_tree(tmp_path)
    monkeypatch.setattr(glob, "glob", _fake_glob(good, empty, text))
    exec(compile(audit.LEDGER_REMOTE, "LEDGER_REMOTE", "exec"), {})
    rows = json.loads(capsys.readouterr().out)
    skipped = {r["db"]: r["skipped"] for r in rows if "skipped" in r}
    assert str(empty) in skipped and str(text) in skipped
    assert "zero-byte or non-sqlite" in next(iter(skipped.values()))


def test_chain_blob_skips_non_sqlite(tmp_path, monkeypatch, capsys):
    good = tmp_path / "data" / "live" / "chain.db"
    good.parent.mkdir(parents=True)
    con = sqlite3.connect(good)
    con.execute("CREATE TABLE block (height INTEGER, hash TEXT)")
    con.execute('CREATE TABLE "transaction" (tx_hash TEXT, block_height INTEGER)')
    con.execute("INSERT INTO block VALUES (5, 'h')")
    con.commit()
    con.close()
    empty = tmp_path / "data" / "stray" / "chain.db"
    empty.parent.mkdir(parents=True)
    empty.touch()
    monkeypatch.setattr(glob, "glob", _fake_glob(empty, good))
    monkeypatch.setattr(sys, "argv", ["-", json.dumps(["0xabc"])])
    exec(compile(audit.CHAIN_REMOTE, "CHAIN_REMOTE", "exec"), {})
    out = json.loads(capsys.readouterr().out)
    assert out["db"] == str(good)
    assert str(empty) in out["skipped"]


def test_audit_main_reports_skipped_not_fail(monkeypatch, capsys):
    skipped_row = json.dumps(
        [{"db": "/var/lib/aitbc/data/stray/bridge_deposits.db", "skipped": "zero-byte or non-sqlite file"}]
    )
    monkeypatch.setattr(audit, "remote_python", lambda *a, **kw: skipped_row)
    monkeypatch.setattr(sys, "argv", ["bridge-payout-audit.py", "node0=node0"])
    assert audit.main() == 0
    out = capsys.readouterr().out
    assert "skipped (zero-byte or non-sqlite file)" in out
    assert "FAIL" not in out
