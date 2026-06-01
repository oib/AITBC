"""Database connection and session management for Hermes service."""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .schema import Base

# Database path
DB_PATH = os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/hermes_coin_requests.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False
        )
    return _engine


def init_db():
    """Initialize database and create tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_session_local():
    """Get session local factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


@contextmanager
def get_db_session():
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
