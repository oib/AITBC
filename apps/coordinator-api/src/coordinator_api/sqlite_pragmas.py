"""SQLite WAL + busy_timeout pragmas for coordinator-api engines (#1560).

Every pooled sqlite connection gets ``journal_mode=WAL``,
``synchronous=NORMAL`` and a 30s ``busy_timeout`` via the SQLAlchemy
``connect`` event. WAL is persistent per database file; the busy timeout
is per-connection, so it must be applied on each new connection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import AsyncEngine

SQLITE_BUSY_TIMEOUT_MS = 30_000


def _apply_sqlite_pragmas(dbapi_connection: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def install_sqlite_pragmas(engine: Engine | AsyncEngine) -> None:
    """Attach the pragma hook to every new pooled connection.

    No-op for non-sqlite dialects (and for duck-typed test doubles that
    are not engines at all). ``AsyncEngine`` events are registered on its
    ``sync_engine`` — the aiosqlite adapter's connect hook still receives
    a cursor-capable connection (verified: the pragma executes and
    ``journal_mode`` persists as ``wal``).
    """
    target = getattr(engine, "sync_engine", engine)
    if getattr(getattr(target, "dialect", None), "name", None) != "sqlite":
        return
    event.listen(target, "connect", lambda dbapi_conn, _record: _apply_sqlite_pragmas(dbapi_conn))
