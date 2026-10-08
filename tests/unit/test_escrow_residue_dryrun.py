"""Fixture tests for escrow_residue_dryrun.py + escrow-residue-textfile.py (S-11)."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dryrun = _load("escrow_residue_dryrun", REPO / "scripts/ops/escrow_residue_dryrun.py")
exporter = _load("escrow_residue_textfile", REPO / "scripts/monitoring/escrow-residue-textfile.py")

NOW = 1_800_000_000.0
FEE_RECIPIENT = "0x34fFfAd1111111111111111111111111111111AA"
CUSTODY = "0x9999999999999999999999999999999999999999"


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute(
        """CREATE TABLE escrow (job_id TEXT PRIMARY KEY, chain_id TEXT, buyer TEXT, provider TEXT,
               amount INTEGER, status TEXT, created_at TEXT, released_at TEXT, refunded_at TEXT,
               lock_tx_hash TEXT, released_amount INTEGER, refunded_amount INTEGER)"""
    )
    con.execute('CREATE TABLE "transaction" (hash TEXT PRIMARY KEY, payload TEXT)')
    con.execute(
        "CREATE TABLE chain_parameter (id INTEGER PRIMARY KEY, chain_id TEXT, parameter TEXT, value TEXT, applied_height INTEGER)"
    )
    con.execute("INSERT INTO chain_parameter VALUES (1, 'c', 'escrow_fee_recipient', ?, 100)", (FEE_RECIPIENT,))
    con.execute(
        'INSERT INTO "transaction" VALUES (?, ?)',
        ("lockhash1", json.dumps({"job_id": "stale-job", "to": CUSTODY, "action": "lock"})),
    )
    # stale released row: fee leg stranded 30 days ago
    con.execute(
        "INSERT INTO escrow VALUES ('stale-job','c','b','p',1000,'released',NULL,?,NULL,'lockhash1',975,NULL)",
        ("2026-09-01 00:00:00",),
    )
    # fresh released row: residue younger than the threshold
    con.execute(
        "INSERT INTO escrow VALUES ('fresh-job','c','b','p',2000,'released',NULL,?,NULL,NULL,1950,NULL)",
        ("2999-01-01 00:00:00",),
    )
    # clean row: fully accounted, must not appear
    con.execute(
        "INSERT INTO escrow VALUES ('clean-job','c','b','p',500,'refunded',NULL,NULL,?,NULL,NULL,500)",
        ("2026-09-01 00:00:00",),
    )
    # held row: non-terminal residue is not residue
    con.execute("INSERT INTO escrow VALUES ('held-job','c','b','p',700,'held',NULL,NULL,NULL,NULL,NULL,NULL)")
    con.commit()
    con.close()
    return db


def test_collects_stale_residue_with_custody_and_recipient(tmp_path):
    rows, fee = dryrun.collect_residues(str(_db(tmp_path)), now=NOW, min_age_seconds=604800)
    stale = [r for r in rows if r.stale]
    fresh = [r for r in rows if not r.stale]
    assert [r.job_id for r in stale] == ["stale-job"]
    assert stale[0].residue == 25
    assert stale[0].custody_address == CUSTODY
    assert [r.job_id for r in fresh] == ["fresh-job"]  # informational only
    assert fee == FEE_RECIPIENT


def test_sweep_leg_shape(tmp_path):
    rows, fee = dryrun.collect_residues(str(_db(tmp_path)), now=NOW, min_age_seconds=604800)
    leg = dryrun.sweep_leg(rows[0], fee)
    assert leg["type"] == "ESCROW_FEE_SWEEP"
    assert leg["payload"]["job_id"] == "stale-job"
    assert leg["value_units"] == 25
    assert leg["to"] == FEE_RECIPIENT
    assert "never submits" in leg["note"]


def test_fee_recipient_override_and_placeholder(tmp_path):
    db = tmp_path / "noparam.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE escrow (job_id TEXT PRIMARY KEY, chain_id TEXT, amount INTEGER, status TEXT, created_at TEXT, released_at TEXT, refunded_at TEXT, lock_tx_hash TEXT, released_amount INTEGER, refunded_amount INTEGER)"
    )
    con.execute('CREATE TABLE "transaction" (hash TEXT PRIMARY KEY, payload TEXT)')
    con.execute("INSERT INTO escrow VALUES ('j','c',100,'released',NULL,'2026-09-01 00:00:00',NULL,NULL,97,NULL)")
    con.commit()
    con.close()
    rows, fee = dryrun.collect_residues(str(db), now=NOW, min_age_seconds=1)
    assert fee is None
    assert dryrun.sweep_leg(rows[0], fee)["to"] == "<escrow_fee_recipient unset>"


def test_exporter_counts_only_stale(tmp_path):
    db = _db(tmp_path)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = exporter.stale_residues(con, now=NOW, max_age_seconds=604800)
    con.close()
    assert len(rows) == 1 and rows[0].job_id == "stale-job" and rows[0].residue == 25


def test_exporter_render_marks_failed_db(tmp_path):
    text = exporter.render({"/good/chain.db": [], "/bad/chain.db": None}, now=NOW)
    assert 'aitbc_escrow_residue_scrape_success{db="/good/chain.db"} 1' in text
    assert 'aitbc_escrow_residue_scrape_success{db="/bad/chain.db"} 0' in text
    assert "aitbc_escrow_residue_accounts 0" in text


def test_exporter_render_lists_stale_rows(tmp_path):
    text = exporter.render(
        {"/db/chain.db": [exporter.ResidueRow(job_id="stale-job", residue=25, age_seconds=3000000)]},
        now=NOW,
    )
    assert "aitbc_escrow_residue_accounts 1" in text
    assert 'job_id="stale-job"' in text
    assert "aitbc_escrow_residue_oldest_seconds 3000000" in text


def test_main_table_lists_and_never_writes(tmp_path, capsys):
    db = _db(tmp_path)
    rc = dryrun.main(["--db", str(db), "--min-age-seconds", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "stale-jo" in out and "submits nothing" in out


def test_json_output_emits_legs(tmp_path, capsys):
    db = _db(tmp_path)
    dryrun.main(["--db", str(db), "--json"])
    doc = json.loads(capsys.readouterr().out)
    stale = [r for r in doc["residues"] if r["stale"]]
    assert stale[0]["sweep_leg"]["type"] == "ESCROW_FEE_SWEEP"
    assert doc["fee_recipient"] == FEE_RECIPIENT
