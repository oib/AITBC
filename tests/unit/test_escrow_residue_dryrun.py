"""Fixture tests for escrow_residue_dryrun.py + escrow-residue-textfile.py (S-11/S-12)."""

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
PAYEE = "0x9999999999999999999999999999999999999999"
V3 = 5470


def _tx(con, tx_hash, tx_type, height, value, job_id, extra=None):
    payload = {"job_id": job_id, "to": PAYEE}
    if extra:
        payload.update(extra)
    con.execute('INSERT INTO "transaction" VALUES (?,?,?,?,?)', (tx_hash, tx_type, height, value, json.dumps(payload)))


def _db(tmp_path: Path) -> Path:
    """Chain fixture: one job per residue class."""
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute(
        """CREATE TABLE escrow (job_id TEXT PRIMARY KEY, chain_id TEXT, buyer TEXT, provider TEXT,
               amount INTEGER, status TEXT, created_at TEXT, released_at TEXT, refunded_at TEXT,
               lock_tx_hash TEXT, released_amount INTEGER, refunded_amount INTEGER)"""
    )
    con.execute(
        'CREATE TABLE "transaction" (tx_hash TEXT PRIMARY KEY, type TEXT, block_height INTEGER, value INTEGER, payload TEXT)'
    )
    con.execute(
        "CREATE TABLE chain_parameter (id INTEGER PRIMARY KEY, chain_id TEXT, parameter TEXT, value TEXT, applied_height INTEGER)"
    )
    con.execute("INSERT INTO chain_parameter VALUES (1, 'c', 'escrow_fee_recipient', ?, 100)", (FEE_RECIPIENT,))
    # fee leg: v3 lock, only partial release — residue still in custody
    _tx(con, "l-fee", "ESCROW_LOCK", 6000, 1000, "fee-job")
    _tx(con, "r-fee", "ESCROW_RELEASE", 6010, 975, "fee-job")
    con.execute(
        "INSERT INTO escrow VALUES ('fee-job','c','b','p',1000,'released',NULL,?,NULL,'l-fee',975,NULL)",
        ("2026-09-01 00:00:00",),
    )
    # already settled: second release covered the residue; ledger never wrote back
    _tx(con, "l-set", "ESCROW_LOCK", 7000, 1000, "settled-job")
    _tx(con, "r1-set", "ESCROW_RELEASE", 7010, 975, "settled-job")
    _tx(con, "r2-set", "ESCROW_RELEASE", 8000, 25, "settled-job")
    con.execute(
        "INSERT INTO escrow VALUES ('settled-job','c','b','p',1000,'released',NULL,?,NULL,'l-set',975,NULL)",
        ("2026-09-01 00:00:00",),
    )
    # already fee-swept
    _tx(con, "l-swp", "ESCROW_LOCK", 7000, 1000, "swept-job")
    _tx(con, "r-swp", "ESCROW_RELEASE", 7010, 975, "swept-job")
    _tx(con, "s-swp", "ESCROW_FEE_SWEEP", 7020, 25, "swept-job")
    con.execute(
        "INSERT INTO escrow VALUES ('swept-job','c','b','p',1000,'released',NULL,?,NULL,'l-swp',975,NULL)",
        ("2026-09-01 00:00:00",),
    )
    # v2 lock: below custody height — authority retained the fee
    _tx(con, "l-v2", "ESCROW_LOCK", 1000, 1000, "v2-job")
    _tx(con, "r-v2", "ESCROW_RELEASE", 1010, 975, "v2-job")
    con.execute(
        "INSERT INTO escrow VALUES ('v2-job','c','b','p',1000,'released',NULL,?,NULL,'l-v2',975,NULL)",
        ("2026-09-01 00:00:00",),
    )
    # void, never locked: no legs at all
    con.execute(
        "INSERT INTO escrow VALUES ('void-job','c','b','p',3600,'void','2026-09-01 00:00:00',NULL,NULL,NULL,NULL,NULL)"
    )
    # canary: residue already released, flagged by name
    _tx(con, "l-can", "ESCROW_LOCK", 6000, 100, "canary-job-1")
    _tx(con, "r1-can", "ESCROW_RELEASE", 6010, 97, "canary-job-1")
    _tx(con, "r2-can", "ESCROW_RELEASE", 8000, 3, "canary-job-1")
    con.execute(
        "INSERT INTO escrow VALUES ('canary-job-1','c','b','p',100,'released',NULL,?,NULL,'l-can',97,NULL)",
        ("2026-09-01 00:00:00",),
    )
    con.commit()
    con.close()
    return db


def _residues(db: Path, **kw):
    kw.setdefault("v3_height", V3)
    rows, fee = dryrun.collect_residues(str(db), now=NOW, min_age_seconds=1, **kw)
    return {r.job_id: r for r in rows}, fee


def test_classes_assigned(tmp_path):
    rows, fee = _residues(_db(tmp_path))
    assert rows["fee-job"].cls == "fee leg"
    assert rows["settled-job"].cls == "already settled (released)"
    assert rows["swept-job"].cls == "already settled (fee-swept)"
    assert rows["v2-job"].cls == "v2 authority-retained"
    assert rows["void-job"].cls == "void — never locked"
    assert rows["canary-job-1"].cls == "canary-already settled (released)"
    assert fee == FEE_RECIPIENT


def test_leg_facts_recorded(tmp_path):
    rows, _ = _residues(_db(tmp_path))
    assert rows["settled-job"].lock_height == 7000
    assert rows["settled-job"].sealed_outflow == 1000
    assert rows["void-job"].lock_height is None
    assert rows["void-job"].sealed_outflow == 0


def test_sweep_leg_only_for_fee_legs(tmp_path):
    rows, fee = _residues(_db(tmp_path))
    leg = dryrun.sweep_leg(rows["fee-job"], fee)
    assert leg["type"] == "ESCROW_FEE_SWEEP" and leg["value_units"] == 25
    assert rows["v2-job"].cls != "fee leg"  # v2 rows must never get a leg


def test_rounding_dust_class(tmp_path):
    db = tmp_path / "dust.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE escrow (job_id TEXT PRIMARY KEY, chain_id TEXT, amount INTEGER, status TEXT, created_at TEXT, released_at TEXT, refunded_at TEXT, lock_tx_hash TEXT, released_amount INTEGER, refunded_amount INTEGER)"
    )
    con.execute(
        'CREATE TABLE "transaction" (tx_hash TEXT PRIMARY KEY, type TEXT, block_height INTEGER, value INTEGER, payload TEXT)'
    )
    con.execute(
        'INSERT INTO "transaction" VALUES (?,?,?,?,?)',
        ("l-d", "ESCROW_LOCK", 6000, 1000, json.dumps({"job_id": "d-job"})),
    )
    con.execute("INSERT INTO escrow VALUES ('d-job','c',1000,'released',NULL,'2026-09-01 00:00:00',NULL,'l-d',997,NULL)")
    con.commit()
    con.close()
    rows, _ = _residues(db, dust=5)
    assert rows["d-job"].cls == "rounding dust"


def test_exporter_counts_only_stale(tmp_path):
    db = _db(tmp_path)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = exporter.stale_residues(con, now=NOW, max_age_seconds=604800)
    con.close()
    assert len(rows) == 6 and {r.job_id for r in rows} == {
        "fee-job",
        "settled-job",
        "swept-job",
        "v2-job",
        "void-job",
        "canary-job-1",
    }


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


def test_main_table_shows_classes(tmp_path, capsys):
    db = _db(tmp_path)
    rc = dryrun.main(["--db", str(db), "--min-age-seconds", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fee leg" in out and "void — never locked" in out and "classes:" in out


def test_json_output_emits_legs_only_for_fee_class(tmp_path, capsys):
    db = _db(tmp_path)
    dryrun.main(["--db", str(db), "--json"])
    doc = json.loads(capsys.readouterr().out)
    by_id = {r["job_id"]: r for r in doc["residues"]}
    assert by_id["fee-job"]["sweep_leg"]["type"] == "ESCROW_FEE_SWEEP"
    assert by_id["v2-job"]["sweep_leg"] is None
    assert by_id["void-job"]["sweep_leg"] is None
    assert doc["fee_recipient"] == FEE_RECIPIENT
