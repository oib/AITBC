"""Tests for scripts/ops/escrow-stuck-sweep.py — the read-only stuck-lock monitor.

Builds a fixture chain.db (``escrow`` + ``transaction``) and a fixture
coordinator.db (``job`` + ``job_payments``) and pins the two things the sweep
exists for: a locked escrow counts as stuck only when its job is terminal AND
the lock is older than ``--max-age``, and every connection is ``mode=ro``.
"""

import importlib.util
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "escrow-stuck-sweep.py"

NOW = datetime.now(UTC)
OLD = (NOW - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S.%f")
FRESH = (NOW - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S.%f")


def _load():
    spec = importlib.util.spec_from_file_location("escrow_stuck_sweep", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["escrow_stuck_sweep"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _mk_chain(path: Path, escrows: list[dict], txs: list[tuple[str, dict]]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE escrow (
            job_id VARCHAR PRIMARY KEY, chain_id VARCHAR, buyer VARCHAR,
            provider VARCHAR, amount INTEGER, status VARCHAR, created_at DATETIME,
            released_at DATETIME, refunded_at DATETIME, lock_tx_hash VARCHAR,
            job_tx_hash VARCHAR, release_tx_hash VARCHAR, refund_tx_hash VARCHAR)"""
    )
    conn.execute(
        'CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, chain_id VARCHAR, '
        "tx_hash VARCHAR, type VARCHAR, status VARCHAR, payload JSON, tx_metadata VARCHAR)"
    )
    for e in escrows:
        conn.execute(
            "INSERT INTO escrow (job_id, chain_id, buyer, provider, amount, status, "
            "created_at, job_tx_hash) VALUES (?,?,?,?,?,?,?,?)",
            (
                e["job_id"],
                "bc-2",
                "0x" + "11" * 20,
                "0x" + "22" * 20,
                e["amount"],
                e.get("status", "locked"),
                e.get("created_at", OLD),
                e.get("job_tx_hash"),
            ),
        )
    for i, (ttype, meta) in enumerate(txs):
        conn.execute(
            'INSERT INTO "transaction" (id, chain_id, tx_hash, type, status, tx_metadata) VALUES (?,?,?,?,?,?)',
            (i, "bc-2", f"0x{i:064x}", ttype, "confirmed", json.dumps(meta)),
        )
    conn.commit()
    conn.close()


def _mk_coord(path: Path, jobs: list[tuple[str, str]], payments: list[tuple[str, str]]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE job (id VARCHAR PRIMARY KEY, state VARCHAR(20))")
    conn.execute("CREATE TABLE job_payments (id VARCHAR PRIMARY KEY, job_id VARCHAR, status VARCHAR(20))")
    for jid, state in jobs:
        conn.execute("INSERT INTO job (id, state) VALUES (?,?)", (jid, state))
    for i, (jid, status) in enumerate(payments):
        conn.execute("INSERT INTO job_payments (id, job_id, status) VALUES (?,?,?)", (f"p{i}", jid, status))
    conn.commit()
    conn.close()


@pytest.fixture()
def dbs(tmp_path):
    chain = tmp_path / "chain.db"
    coord = tmp_path / "coordinator.db"
    _mk_chain(
        chain,
        [
            # stuck: terminal job, old lock
            {"job_id": "job_done_old", "amount": 60000},
            {"job_id": "job_failed_old", "amount": 36000},
            # not stuck: terminal but fresh
            {"job_id": "job_done_fresh", "amount": 36000, "created_at": FRESH},
            # not stuck: old but job still running
            {"job_id": "job_running_old", "amount": 72000},
            # not stuck: old, no job row anywhere, no chain evidence
            {"job_id": "job_unknown_old", "amount": 36000},
            # stuck via payment evidence only (no job row)
            {"job_id": "job_payonly_old", "amount": 36000},
            # settled already — never listed
            {"job_id": "job_released", "amount": 36000, "status": "released"},
            # stuck via sealed release leg the row missed
            {"job_id": "job_sealed_old", "amount": 36000},
        ],
        [("ESCROW_LOCK", {"job_id": "job_sealed_old"}), ("ESCROW_RELEASE", {"job_id": "job_sealed_old"})],
    )
    _mk_coord(
        coord,
        [
            ("job_done_old", "COMPLETED"),
            ("job_failed_old", "FAILED"),
            ("job_done_fresh", "COMPLETED"),
            ("job_running_old", "RUNNING"),
        ],
        [("job_payonly_old", "settlement_failed")],
    )
    return chain, coord


def _run(tool, *argv):
    return tool.main(list(argv))


def test_stuck_terminal_and_age(tool, dbs, capsys):
    chain, coord = dbs
    rc = _run(tool, "--chain-db", str(chain), "--coordinator-db", str(coord), "--marketplace-db", "/nonexistent")
    out = capsys.readouterr().out
    assert rc == 1
    assert "job_done_old" in out
    assert "job_failed_old" in out
    assert "job_payonly_old" in out  # terminal via job_payments
    assert "job_sealed_old" in out  # terminal via sealed settle leg
    assert "job_released" not in out  # settled rows are not locks


def test_age_grace_and_active_jobs_not_stuck(tool, dbs, capsys):
    chain, coord = dbs
    rc = _run(tool, "--chain-db", str(chain), "--coordinator-db", str(coord), "--json")
    data = json.loads(capsys.readouterr().out)
    stuck_ids = {r["job_id"] for r in data["stuck"]}
    other_ids = {r["job_id"] for r in data["locked_other"]}
    assert rc == 1
    assert "job_done_fresh" in other_ids  # terminal but within --max-age
    assert "job_running_old" in other_ids  # old but still active
    assert "job_unknown_old" in other_ids  # no evidence either way
    assert "job_sealed_old" in stuck_ids


def test_clean_exit_zero(tool, dbs, capsys):
    chain, coord = dbs
    # 4h max-age clears every fixture row (oldest is 3h).
    rc = _run(tool, "--chain-db", str(chain), "--coordinator-db", str(coord), "--max-age", "14400")
    assert rc == 0


def test_missing_db_exit_two(tool, tmp_path, capsys):
    rc = _run(tool, "--chain-db", str(tmp_path / "nope.db"))
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_textfile_output(tool, dbs, tmp_path, capsys):
    chain, coord = dbs
    prom = tmp_path / "aitbc_escrow_stuck.prom"
    _run(tool, "--chain-db", str(chain), "--coordinator-db", str(coord), "--textfile", str(prom))
    text = prom.read_text()
    assert "aitbc_escrow_stuck_locks 4" in text
    assert 'aitbc_escrow_stuck_lock{job_id="job_done_old"} 1' in text
    assert "aitbc_escrow_stuck_lock_oldest_seconds" in text
    assert "aitbc_escrow_stuck_scrape_success" in text


def test_readonly_connection_refuses_writes(tool, dbs):
    chain, _ = dbs
    src = tool.Source(str(chain))
    with pytest.raises(sqlite3.OperationalError):
        src.query("INSERT INTO escrow (job_id) VALUES ('x')")
