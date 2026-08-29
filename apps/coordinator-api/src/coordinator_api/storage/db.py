"""
Unified database configuration for AITBC Coordinator API

Provides SQLite and PostgreSQL support with connection pooling.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Session
from sqlalchemy.pool import QueuePool

from aitbc.aitbc_logging import get_logger

from ..config import settings

logger = get_logger(__name__)

_engine = None
_async_engine = None


def get_engine() -> Engine:
    """Get or create the database engine with connection pooling."""
    global _engine
    if _engine is None:
        effective_url = settings.database.effective_url
        if "sqlite" in effective_url:
            _engine = create_engine(
                effective_url,
                echo=settings.db_echo,
                connect_args={"check_same_thread": False},
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=settings.db_pool_pre_ping,
            )
        else:
            _engine = create_engine(
                effective_url,
                echo=settings.db_echo,
                poolclass=QueuePool,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_recycle=settings.db_pool_recycle,
                pool_pre_ping=settings.db_pool_pre_ping,
            )
    return _engine


def init_db() -> Engine:
    """Initialize database engine and ensure the SQLite data directory exists.

    Schema management is Alembic's job. Do not call create_all() here; it can
    create unmanaged schema objects that drift from the migration graph.
    """
    engine = get_engine()
    if "sqlite" in str(engine.url):
        db_path = engine.url.database
        if db_path:
            from pathlib import Path

            if db_path.startswith("./"):
                db_path = db_path[2:]
            data_dir = Path(db_path).parent
            data_dir.mkdir(parents=True, exist_ok=True)
    return engine


@contextmanager
def session_scope() -> Generator[Session]:
    """Context manager for database sessions."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


def get_session() -> Generator[Session]:
    """Get a database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


async def get_async_engine() -> AsyncEngine:
    """Get or create async database engine."""
    global _async_engine
    if _async_engine is None:
        db_config = settings.database
        effective_url = db_config.effective_url
        if "sqlite" in effective_url:
            async_url = effective_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        else:
            async_url = effective_url.replace("postgresql://", "postgresql+asyncpg://")
        _async_engine = create_async_engine(
            async_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=settings.db_pool_pre_ping,
        )
    return _async_engine


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession]:
    """Async context manager for database sessions."""
    engine = await get_async_engine()
    async with AsyncSession(engine) as session:
        yield session


async def get_async_session() -> AsyncSession:
    """Get an async database session."""
    engine = await get_async_engine()
    return async_sessionmaker(engine)()


async def init_async_db() -> None:
    """Initialize async database engine.

    Schema management is Alembic's job. Do not call create_all() here; it can
    create unmanaged schema objects that drift from the migration graph.
    """
    engine = await get_async_engine()
    # Just ensure the engine is created; schema is managed by Alembic.
    _ = engine
