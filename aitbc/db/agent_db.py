"""Database connection and session management for coin requests.

Moved from hermes_service.storage.database in v0.5.9 §1
to provide shared DB access for both the Agent Coordinator and CLI.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from aitbc.models import Base


def get_db_path() -> str:
    """Get database path from environment variable."""
    return os.getenv("AGENT_DB_PATH", os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/agent_coin_requests.db"))


def get_database_url() -> str:
    """Get database URL dynamically."""
    db_path = get_db_path()
    return f"sqlite:///{db_path}"


_engine = None
_SessionLocal = None


def get_engine() -> Engine:
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), connect_args={"check_same_thread": False}, echo=False)
    return _engine


def init_db() -> None:
    """Initialize database and create tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_session_local() -> sessionmaker[Session]:
    """Get session local factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
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
