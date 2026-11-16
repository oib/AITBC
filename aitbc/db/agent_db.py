"""Database connection and session management for coin requests.

Moved from hermes_service.storage.database in v0.5.9 §1
to provide shared DB access for both the Agent Coordinator and CLI.
"""

import os
from collections.abc import Generator
from pathlib import Path
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from aitbc.models import Base

SQLITE_BUSY_TIMEOUT_MS = 30_000


def _env_file_db_hits(env_file: Path) -> tuple[list[str], list[str]]:
    """Return (AGENT_DB_PATH values, HERMES_DB_PATH values) set in one env file."""
    agent_hits: list[str] = []
    hermes_hits: list[str] = []
    try:
        lines = env_file.read_text().splitlines()
    except OSError:
        return agent_hits, hermes_hits
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip().strip('"').strip("'")
        if not value:
            continue
        if key.strip() == "AGENT_DB_PATH":
            agent_hits.append(value)
        elif key.strip() == "HERMES_DB_PATH":
            hermes_hits.append(value)
    return agent_hits, hermes_hits


def _service_env_db_path() -> str | None:
    """Resolve the ledger path from the service env files under /etc/aitbc.

    The CLI and services run in different environments: a systemd unit gets
    AGENT_DB_PATH from its EnvironmentFile while an interactive ``aitbc``
    invocation does not. Scan /etc/aitbc/*.env so ``aitbc coin-requests``
    lands on the same ledger the coordinator writes — preferring the
    coordinator-api file (the hermes coin-request ledger) over the
    agent-coordinator one.
    """
    etc_dir = Path("/etc/aitbc")
    if not etc_dir.is_dir():
        return None
    agent_hits: list[tuple[str, str]] = []  # (filename, path)
    hermes_hits: list[tuple[str, str]] = []
    try:
        env_files = sorted(etc_dir.glob("*.env"))
    except OSError:
        return None
    for env_file in env_files:
        agent_vals, hermes_vals = _env_file_db_hits(env_file)
        agent_hits.extend((env_file.name, v) for v in agent_vals)
        hermes_hits.extend((env_file.name, v) for v in hermes_vals)
    for hits in (agent_hits, hermes_hits):
        for name, path in hits:
            if "coordinator-api" in name:
                return path
    for hits in (agent_hits, hermes_hits):
        if hits:
            return hits[0][1]
    return None


def get_db_path() -> str:
    """Get database path from environment variable or service env files."""
    explicit = os.getenv("AGENT_DB_PATH") or os.getenv("HERMES_DB_PATH")
    if explicit:
        return explicit
    return _service_env_db_path() or "/var/lib/aitbc/data/agent_coin_requests.db"


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
