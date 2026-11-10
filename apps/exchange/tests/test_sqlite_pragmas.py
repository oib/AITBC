"""#1560: exchange sqlite connections must run WAL + a 30s busy timeout."""

from __future__ import annotations

from apps.exchange.simple_exchange.db import connect_db


def test_connect_db_enables_wal_and_busy_timeout(tmp_path) -> None:
    db_path = str(tmp_path / "exchange.db")
    conn = connect_db(db_path)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    finally:
        conn.close()


def test_connect_db_default_path_uses_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite:///{tmp_path}/env.db")
    conn = connect_db()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()
