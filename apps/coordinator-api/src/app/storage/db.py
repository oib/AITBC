"""
Unified database configuration for AITBC Coordinator API

Provides SQLite and PostgreSQL support with connection pooling.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextlib import asynccontextmanager
from typing import Generator, AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from sqlmodel import SQLModel

from ..config import settings

_engine = None
_async_engine = None


def get_engine() -> Engine:
    """Get or create the database engine with connection pooling."""
    global _engine

    if _engine is None:
        # Allow tests to override via settings.database_url (fixtures set this directly)
        db_override = getattr(settings, "database_url", None)

        db_config = settings.database
        effective_url = db_override or db_config.effective_url

        if "sqlite" in effective_url:
            _engine = create_engine(
                effective_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_engine(
                effective_url,
                echo=False,
                pool_size=db_config.pool_size,
                max_overflow=db_config.max_overflow,
                pool_pre_ping=db_config.pool_pre_ping,
            )
    return _engine


def init_db() -> Engine:
    """Initialize database tables and ensure data directory exists."""
    engine = get_engine()
    
    # Ensure data directory exists for SQLite (consistent with blockchain-node pattern)
    if "sqlite" in str(engine.url):
        db_path = engine.url.database
        if db_path:
            from pathlib import Path
            # Extract directory path from database file path
            if db_path.startswith("./"):
                db_path = db_path[2:]  # Remove ./
            data_dir = Path(db_path).parent
            data_dir.mkdir(parents=True, exist_ok=True)
    
    SQLModel.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


# Dependency for FastAPI
SessionDep = Session


def get_session() -> Session:
    """Get a database session."""
    engine = get_engine()
    return Session(engine)


# Async support for future use
async def get_async_engine() -> AsyncEngine:
    """Get or create async database engine."""
    global _async_engine

    if _async_engine is None:
        db_config = settings.database
        effective_url = db_config.effective_url

        # Convert SQLite to async SQLite
        if "sqlite" in effective_url:
            async_url = effective_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        else:
            # Convert PostgreSQL to async PostgreSQL
            async_url = effective_url.replace("postgresql://", "postgresql+asyncpg://")

        _async_engine = create_async_engine(
            async_url,
            echo=False,
            pool_size=db_config.pool_size,
            max_overflow=db_config.max_overflow,
            pool_pre_ping=db_config.pool_pre_ping,
        )
    return _async_engine


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions."""
    engine = await get_async_engine()
    async with AsyncSession(engine) as session:
        yield session


async def get_async_session() -> AsyncSession:
    """Get an async database session."""
    engine = await get_async_engine()
    return async_sessionmaker(engine)()
