"""Task 96/98: the known-artifact registry for open tx-only escrow locks.

Six pre-v3 ESCROW_LOCK transactions (blocks 1262-1598, Sep-10 test era) have
no release/refund leg, no escrow row, and no custody balance. Nothing
automated saw them: the settlement detector reads the escrow table, the
sweepers read coordinator/market rows, and the pooled value blends into the
supply sum. ``escrow-known-artifacts.yml`` records their disposition; the
textfile exporter's tx-level scan surfaces any *unregistered* open tx-only
lock via ``aitbc_escrow_open_tx_only_lock``.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

MONITORING = Path(__file__).resolve().parents[2] / "scripts" / "monitoring"
REGISTRY = MONITORING / "escrow-known-artifacts.yml"

_spec = importlib.util.spec_from_file_location("escrow_settlements_textfile", MONITORING / "escrow-settlements-textfile.py")
assert _spec is not None and _spec.loader is not None
exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exporter)

OPEN_LOCKS = {
    "sw_job_20260910163039_207d09b8": 60_912,
    "sw_job_20260910163341_207d09b8": 25_056,
    "sw_job_20260910163355_88d364d9": 18_000,
    "ipfs_rental_20260910144545_e01131a8": 36_000_000,
    "sw_job_20260910203053_207d09b8": 60_500,
    "edge-test-002": 36_000,
}


def test_registry_names_all_six_open_locks():
    """The registry names every open tx-only lock with a documented reason.

    The file is JSON-in-YAML (valid YAML 1.2): stdlib json parses it, so the
    exporter stays dependency-free while yaml.safe_load reads it identically.
    """
    entries = json.loads(REGISTRY.read_text())["artifacts"]
    by_job = {e["job_id"]: e for e in entries}
    assert set(OPEN_LOCKS) <= set(by_job)
    for job_id in OPEN_LOCKS:
        entry = by_job[job_id]
        assert entry["kind"] == "test-artifact"
        assert entry["reason"], f"{job_id} has no documented reason"
        assert entry["declared_by"] and entry["declared_at"]


def _fixture_db(tmp_path: Path, txs: list[tuple[str, str, str]], escrow_jobs: list[str] | None = None) -> Path:
    """A minimal chain.db: transaction + escrow tables, txs as (hash, type, payload)."""
    db = tmp_path / "data" / "ait-test" / "chain.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE 'transaction' (tx_hash TEXT, type TEXT, payload TEXT)")
    conn.execute(
        "CREATE TABLE escrow (job_id TEXT PRIMARY KEY, status TEXT, release_tx_hash TEXT, "
        "refund_tx_hash TEXT, released_at TEXT, refunded_at TEXT)"
    )
    conn.executemany("INSERT INTO 'transaction' (tx_hash, type, payload) VALUES (?,?,?)", txs)
    conn.executemany("INSERT INTO escrow (job_id, status) VALUES (?, 'locked')", [(j,) for j in (escrow_jobs or [])])
    conn.commit()
    conn.close()
    return db


def _run_main(monkeypatch, tmp_path: Path, registry: str) -> tuple[int, str]:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(out))
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AITBC_CHAIN_DB", raising=False)
    monkeypatch.setenv("AITBC_ESCROW_KNOWN_ARTIFACTS", registry)
    rc = exporter.main()
    return rc, (out / exporter.OUTPUT_NAME).read_text()


def _lock_tx(job_id: str, n: int = 0) -> tuple[str, str, str]:
    return (f"0xlock{n}", "ESCROW_LOCK", json.dumps({"job_id": job_id}))


class TestOpenTxOnlyLocks:
    def test_unregistered_open_lock_is_emitted(self, tmp_path, monkeypatch):
        """A tx-only lock not in the registry must surface — it is the only
        path by which a new abandoned lock would ever alert."""
        _fixture_db(tmp_path, [_lock_tx("fixture-job-001")])
        rc, text = _run_main(monkeypatch, tmp_path, str(REGISTRY))
        assert rc == 0
        assert "aitbc_escrow_open_tx_only_locks 1" in text
        assert 'aitbc_escrow_open_tx_only_lock{job_id="fixture-job-001"} 1' in text

    def test_all_six_registered_locks_are_suppressed(self, tmp_path, monkeypatch):
        """Reproducing the fleet fixture: all six known locks scanned, none emitted."""
        _fixture_db(tmp_path, [_lock_tx(job, i) for i, job in enumerate(OPEN_LOCKS)])
        rc, text = _run_main(monkeypatch, tmp_path, str(REGISTRY))
        assert rc == 0
        assert "aitbc_escrow_open_tx_only_locks 0" in text
        assert "aitbc_escrow_open_tx_only_lock{" not in text

    def test_settled_lock_is_not_open(self, tmp_path, monkeypatch):
        _fixture_db(
            tmp_path,
            [_lock_tx("done-job"), ("0xrel", "ESCROW_RELEASE", json.dumps({"job_id": "done-job"}))],
        )
        rc, text = _run_main(monkeypatch, tmp_path, str(REGISTRY))
        assert rc == 0 and "aitbc_escrow_open_tx_only_locks 0" in text

    def test_lock_with_escrow_row_is_not_tx_only(self, tmp_path, monkeypatch):
        """A lock whose job has an escrow row belongs to the row-level check."""
        _fixture_db(tmp_path, [_lock_tx("row-job")], escrow_jobs=["row-job"])
        rc, text = _run_main(monkeypatch, tmp_path, str(REGISTRY))
        assert rc == 0 and "aitbc_escrow_open_tx_only_locks 0" in text

    def test_unreadable_registry_is_failure_not_all_clear(self, tmp_path, monkeypatch):
        """A registry that cannot be read suppresses nothing and must not
        emit the unsuppressed list — it reports as a scrape failure instead."""
        _fixture_db(tmp_path, [_lock_tx("fixture-job-001")])
        missing = str(tmp_path / "no-such-registry.yml")
        rc, text = _run_main(monkeypatch, tmp_path, missing)
        assert rc == 1
        assert f'aitbc_escrow_settlement_scrape_success{{db="{missing}"}} 0' in text
        assert "aitbc_escrow_open_tx_only_lock{" not in text

    def test_malformed_registry_is_failure_not_all_clear(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.yml"
        bad.write_text("{ this is not json or yaml ")
        _fixture_db(tmp_path, [_lock_tx("fixture-job-001")])
        rc, text = _run_main(monkeypatch, tmp_path, str(bad))
        assert rc == 1
        assert "aitbc_escrow_open_tx_only_lock{" not in text
