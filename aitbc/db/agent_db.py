"""Database connection and session management for coin requests.

Moved from hermes_service.storage.database in v0.5.9 §1
to provide shared DB access for both the Agent Coordinator and CLI.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from aitbc.models import Base

SQLITE_BUSY_TIMEOUT_MS = 30_000


def get_db_path() -> str:
    """Get database path from environment variable."""
    return os.getenv("AGENT_DB_PATH", os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/agent_coin_requests.db"))


def get_database_url() -> str:
    """Get database URL dynamically."""
    db_path = get_db_path()
    return f"sqlite:///{db_path}"


_engine = None
_SessionLocal = None


def _apply_sqlite_pragmas(dbapi_connection: Any) -> None:
    """Apply WAL + busy_timeout to every pooled sqlite connection (#1751).

    Same pattern as ``coordinator_api.sqlite_pragmas`` (#1560): WAL is
    persistent per database file, but ``busy_timeout``/``synchronous`` are
    per-connection, so they must be set on each new connection. Without this
    the journal mode depended on which raw-sqlite3 path opened the file
    first, and ORM sessions fell back to pysqlite's ~5s default timeout —
    concurrent writers surfaced ``database is locked`` as 500s.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def get_engine() -> Engine:
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), connect_args={"check_same_thread": False}, echo=False)
        if _engine.dialect.name == "sqlite":
            event.listen(_engine, "connect", lambda dbapi_conn, _record: _apply_sqlite_pragmas(dbapi_conn))
    return _engine


def init_db() -> None:
    """Initialize database and create tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_session_local() -> sessionmaker[Session]:
    """Get session local factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_db_session() -> Generator[Session]:
    """Context manager for database sessions."""
    session_local = get_session_local()
    session = session_local()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
