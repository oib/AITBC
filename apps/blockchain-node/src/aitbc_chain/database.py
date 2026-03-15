from __future__ import annotations

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy import event

from .config import settings

# Import all models to ensure they are registered with SQLModel.metadata
from .models import Block, Transaction, Account, Receipt, Escrow  # noqa: F401

_engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)

@event.listens_for(_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=30000000000")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(_engine)


@contextmanager
def session_scope() -> Session:
    with Session(_engine) as session:
        yield session

# Expose engine for escrow routes
engine = _engine
