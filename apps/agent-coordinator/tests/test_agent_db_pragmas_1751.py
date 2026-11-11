"""#1751: the shared agent DB engine must set WAL + busy_timeout itself.

Previously ``journal_mode=WAL`` was applied only by the raw sqlite3 paths
(``agent_stream._agent_db_conn``, ``coin_request_policy``), so the mode
depended on which path opened the file first; ORM sessions then ran with
pysqlite's ~5s default timeout and surfaced ``database is locked``.
"""

from __future__ import annotations

import pytest

from aitbc.db import agent_db


@pytest.fixture
def fresh_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    return agent_db.get_engine()


def test_engine_connections_get_wal_busy_timeout_synchronous(fresh_engine) -> None:
    with fresh_engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        synchronous = conn.exec_driver_sql("PRAGMA synchronous").scalar()
    assert journal_mode == "wal"
    assert busy_timeout == 30_000
    assert synchronous == 1  # NORMAL


def test_pragmas_apply_to_every_pooled_connection(fresh_engine) -> None:
    # busy_timeout/synchronous are per-connection: a second pooled
    # connection must carry them too, not just the first.
    with fresh_engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30_000
    with fresh_engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30_000
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
