"""Fixture tests for scripts/monitoring/bridge-set-textfile.py (A36-4).

Drives the exporter against a temp chain.db and a temp textfile dir;
asserts the five gauges render correctly for degraded and healthy sets,
that the DB open is read-only, and that an unreadable DB reports
scrape_success 0 / exit 1.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/monitoring/bridge-set-textfile.py"
spec = importlib.util.spec_from_file_location("bridge_set_textfile", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = exporter
spec.loader.exec_module(exporter)

CONSENSUS = "0xAA,0xBB,0xCC,0xDD"


def _db(tmp_path: Path, rows: list[tuple[str, int, int, str]], name: str = "chain.db") -> Path:
    """rows: (address, epoch, is_active, registered_at)."""
    d = tmp_path / "data" / "c"  # DATA_DIR/data/<chain>/
    d.mkdir(parents=True, exist_ok=True)
    db = d / name
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE bridge_validators (chain_id TEXT, address TEXT,"
        " public_key TEXT, epoch INTEGER, is_active INTEGER, registered_at TEXT)"
    )
    for addr, epoch, active, ts in rows:
        conn.execute(
            "INSERT INTO bridge_validators VALUES (?,?,?,?,?,?)",
            ("c", addr, "0x04", epoch, active, ts),
        )
    conn.commit()
    conn.close()
    return db


def _run(tmp_path: Path, monkeypatch, **env) -> tuple[int, str]:
    out = tmp_path / "prom"
    out.mkdir(exist_ok=True)
    for k, v in {
        "AITBC_DATA_DIR": str(tmp_path),
        "AITBC_TEXTFILE_DIR": str(out),
        "VALIDATOR_SET": CONSENSUS,
        "BRIDGE_MULTISIG_THRESHOLD": "2",
        "BRIDGE_VALIDATOR_SET_GRACE_PERIOD": "7200",
        **env,
    }.items():
        monkeypatch.setenv(k, v)
    rc = exporter.main([])
    return rc, (out / "aitbc_bridge_set.prom").read_text()


def test_degraded_set_metrics(tmp_path, monkeypatch) -> None:
    old = (datetime.now(UTC) - timedelta(days=21)).isoformat()
    _db(tmp_path, [("0xXX", 0, 1, old), ("0xYY", 0, 1, old)])
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 0
    assert "aitbc_bridge_active_validators 2\n" in text
    assert "aitbc_bridge_possible_signers 0\n" in text
    assert "aitbc_bridge_threshold 2\n" in text
    # Latest epoch never decays (bridge_validator.py:461-525 mirror) —
    # an old but unsuperseded set still reads fresh; only signer drift alerts.
    assert "aitbc_bridge_set_fresh 1\n" in text
    age = float([ln for ln in text.splitlines() if ln.startswith("aitbc_bridge_set_age_seconds")][0].split()[1])
    assert age > 21 * 86400 - 60  # ~21 days — age still surfaces the drift
    assert "aitbc_bridge_set_scrape_success 1\n" in text


def test_latest_epoch_never_decays(tmp_path, monkeypatch) -> None:
    """bridge_validator.py:461-525 mirror: the chain's LATEST epoch is the
    authoritative set and does not decay — supersession, not wall time, is
    the rotation mechanism. A set far past the grace window stays fresh
    while it is still the newest epoch."""
    ancient = (datetime.now(UTC) - timedelta(days=365)).isoformat()
    _db(tmp_path, [(a, 0, 1, ancient) for a in CONSENSUS.split(",")])
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 0
    assert "aitbc_bridge_set_fresh 1\n" in text
    assert "aitbc_bridge_possible_signers 4\n" in text


def test_empty_table_reads_fresh(tmp_path, monkeypatch) -> None:
    """Mirror of the rpc's 'no validators registered -> True' branch: an
    empty table does not trip the freshness gauge; the threshold alert is
    what catches it."""
    d = tmp_path / "data" / "c"
    d.mkdir(parents=True)
    conn = sqlite3.connect(d / "chain.db")
    conn.execute(
        "CREATE TABLE bridge_validators (chain_id TEXT, address TEXT,"
        " public_key TEXT, epoch INTEGER, is_active INTEGER, registered_at TEXT)"
    )
    conn.commit()
    conn.close()
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 0
    assert "aitbc_bridge_set_fresh 1\n" in text
    assert "aitbc_bridge_possible_signers 0\n" in text


def test_prom_file_mode_0644(tmp_path, monkeypatch) -> None:
    """node-exporter scrapes the textfile dir as user prometheus — a
    mkstemp-default 0600 file is invisible to it (permission denied shows
    up as node_textfile_scrape_error, not as a missing metric)."""
    _db(tmp_path, [("0xAA", 0, 1, datetime.now(UTC).isoformat())])
    out = tmp_path / "prom"
    _run(tmp_path, monkeypatch)
    mode = (out / "aitbc_bridge_set.prom").stat().st_mode & 0o777
    assert mode == 0o644, f"prom file mode {mode:o} — must be 0644"


def test_healthy_set_metrics(tmp_path, monkeypatch) -> None:
    fresh = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    _db(tmp_path, [(a, 1, 1, fresh) for a in CONSENSUS.split(",")] + [("0xZZ", 1, 0, fresh)])
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 0
    # 4 active (the inactive 0xZZ excluded), all 4 are consensus members.
    assert "aitbc_bridge_active_validators 4\n" in text
    assert "aitbc_bridge_possible_signers 4\n" in text
    assert "aitbc_bridge_set_fresh 1\n" in text


def test_inactive_rows_and_latest_epoch_only(tmp_path, monkeypatch) -> None:
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    new = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    _db(
        tmp_path,
        [("0xAA", 0, 1, old), ("0xBB", 0, 1, old), ("0xAA", 1, 1, new), ("0xEE", 1, 1, new)],
    )
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 0
    # Latest epoch only: 0xAA + 0xEE -> possible counts just 0xAA.
    assert "aitbc_bridge_active_validators 2\n" in text
    assert "aitbc_bridge_possible_signers 1\n" in text
    # Age is from the NEWEST registration across all epochs (the epoch-1
    # rows), matching the freshness check's MAX(registered_at) semantics.
    age = float([ln for ln in text.splitlines() if ln.startswith("aitbc_bridge_set_age_seconds")][0].split()[1])
    assert age < 7200
    assert "aitbc_bridge_set_fresh 1\n" in text


def test_json_validator_set_env(tmp_path, monkeypatch) -> None:
    fresh = datetime.now(UTC).isoformat()
    _db(tmp_path, [("0xAA", 0, 1, fresh)])
    rc, text = _run(tmp_path, monkeypatch, VALIDATOR_SET='["0xAA", "0xBB"]')
    assert "aitbc_bridge_possible_signers 1\n" in text


def test_parse_consensus_set_csv() -> None:
    assert exporter.parse_consensus_set("0xAA, 0xBB ,0xcc") == {"0xaa", "0xbb", "0xcc"}
    assert exporter.parse_consensus_set("") == set()


def test_parse_consensus_set_json_strings() -> None:
    assert exporter.parse_consensus_set('["0xAA", "0xBB"]') == {"0xaa", "0xbb"}
    # malformed JSON yields the empty set rather than raising
    assert exporter.parse_consensus_set("[{") == set()
    assert exporter.parse_consensus_set("[not-json") == set()


def test_parse_consensus_set_json_objects() -> None:
    raw = '[{"address": "0xAA", "stake": "1000"}, {"address": "0xBB", "stake": "0"}, {"stake": "5"}]'
    assert exporter.parse_consensus_set(raw) == {"0xaa", "0xbb"}


def test_no_db_is_failure(tmp_path, monkeypatch) -> None:
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 1
    assert "aitbc_bridge_set_scrape_success 0\n" in text


def test_unreadable_table_is_failure(tmp_path, monkeypatch) -> None:
    d = tmp_path / "data" / "c"
    d.mkdir(parents=True)
    conn = sqlite3.connect(d / "chain.db")
    conn.execute("CREATE TABLE other (x INTEGER)")
    conn.commit()
    conn.close()
    rc, text = _run(tmp_path, monkeypatch)
    assert rc == 1
    assert "aitbc_bridge_set_scrape_success 0\n" in text
