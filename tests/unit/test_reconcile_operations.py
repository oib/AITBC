"""#1006: --db without --service derives the service, not the file stem."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "reconcile-operations.py"


def _load():
    spec = importlib.util.spec_from_file_location("reconcile_operations", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconcile_operations"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _mk_ledger(path: Path, service: str, keys: list[str]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE operations (
            service TEXT NOT NULL, idempotency_key TEXT NOT NULL,
            operation_type TEXT, request_hash TEXT, allow_adopt INTEGER,
            attempt INTEGER, state TEXT, payload TEXT, response_status INTEGER,
            result_json TEXT, created_at REAL, updated_at REAL,
            lease_expires_at REAL, completed_at REAL, error TEXT,
            PRIMARY KEY (service, idempotency_key))"""
    )
    for k in keys:
        conn.execute(
            "INSERT INTO operations (service, idempotency_key, state, attempt, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (service, k, "uncertain", 1, 0.0, 0.0),
        )
    conn.commit()
    conn.close()


def test_db_run_derives_service_from_contents(tool, tmp_path, capsys):
    db = tmp_path / "market_operations.db"
    _mk_ledger(db, "market", ["KEY-A"])
    sys.argv = ["x", "--db", str(db), "--list-uncertain", "--json"]
    rc = tool.main()
    out = capsys.readouterr().out
    assert rc == 0
    report = json.loads(out)
    assert "market" in report  # service derived from contents, not the stem
    assert "market_operations" not in report
    assert "KEY-A" in out


def test_unresolvable_db_requires_service(tool, tmp_path, capsys):
    db = tmp_path / "mystery.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE operations (service TEXT, idempotency_key TEXT)")
    conn.execute("INSERT INTO operations VALUES ('alpha','k1'),('beta','k2')")
    conn.commit()
    conn.close()
    sys.argv = ["x", "--db", str(db), "--list-uncertain"]
    rc = tool.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "--service" in err
