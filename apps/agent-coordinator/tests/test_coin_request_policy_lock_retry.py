"""#1658 sibling: ``agent_db_granted_since`` retries the fresh-file lock race.

d676916bb gave the budget read the same bounded retry ``_agent_db_conn`` got
in 12ec09406 — a ``database is locked`` during the journal_mode/CREATE window
used to fail OPEN to 0, silently disabling the rolling-window auto-grant
budget for that call. These pins cover the retry-then-succeed and
retry-then-fail-open paths without needing a real lock.
"""

from __future__ import annotations

import sqlite3


from agent_app.services import coin_request_policy


def _ledger(tmp_path) -> str:
    """A real coin_requests sqlite ledger with one approved grant."""
    db_path = str(tmp_path / "agent_coin_requests.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE coin_requests ("
        "id TEXT, sender TEXT, recipient TEXT, amount INTEGER, wallet_address TEXT, "
        "status TEXT, approval_mode TEXT, approved_by TEXT, created_at TEXT, expires_at TEXT)"
    )
    conn.execute(
        "INSERT INTO coin_requests VALUES ('r1','s','hub-coordinator',?, '0xw','APPROVED','automatic','p','2020-01-01','2030-01-01')",
        (coin_request_policy.DEFAULT_AUTO_APPROVE_MAX,),
    )
    conn.commit()
    conn.close()
    return db_path


def test_reads_granted_since_on_healthy_db(tmp_path):
    db_path = _ledger(tmp_path)
    total = coin_request_policy.agent_db_granted_since(db_path, "2019-01-01")
    assert total == coin_request_policy.DEFAULT_AUTO_APPROVE_MAX


def test_locked_read_retries_then_succeeds(tmp_path, monkeypatch):
    """Two 'database is locked' failures must not fail open — the third
    attempt reads the real total."""
    db_path = _ledger(tmp_path)
    real_connect = sqlite3.connect
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", flaky)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    total = coin_request_policy.agent_db_granted_since(db_path, "2019-01-01")
    assert total == coin_request_policy.DEFAULT_AUTO_APPROVE_MAX
    assert calls["n"] == 3


def test_persistent_lock_fails_open_to_zero(tmp_path, monkeypatch):
    """After the bounded retries the read still fails OPEN (returns 0) — a
    wedged ledger must not block the grant path outright."""
    db_path = _ledger(tmp_path)

    def always_locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sqlite3, "connect", always_locked)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert coin_request_policy.agent_db_granted_since(db_path, "2019-01-01") == 0


def test_non_lock_error_does_not_retry(tmp_path, monkeypatch):
    """Only 'database is locked' retries — other errors fail open on the
    first attempt."""
    db_path = _ledger(tmp_path)
    calls = {"n": 0}

    def broken(*args, **kwargs):
        calls["n"] += 1
        raise sqlite3.OperationalError("no such table: coin_requests")

    monkeypatch.setattr(sqlite3, "connect", broken)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert coin_request_policy.agent_db_granted_since(db_path, "2019-01-01") == 0
    assert calls["n"] == 1
