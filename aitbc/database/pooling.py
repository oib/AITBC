"""
SQLAlchemy connection pooling utilities.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def create_pooled_engine(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    echo: bool = False,
    use_static_pool: bool = False,
):
    """
    Create SQLAlchemy engine with connection pooling.

    Args:
        database_url: Database connection URL
        pool_size: Size of connection pool
        max_overflow: Maximum overflow connections
        pool_recycle: Connection recycle time in seconds
        pool_pre_ping: Test connections before using
        echo: Enable SQL query logging
        use_static_pool: Use StaticPool for SQLite (single connection)

    Returns:
        SQLAlchemy engine with connection pooling
    """
    if "sqlite" in database_url and use_static_pool:
        # SQLite with StaticPool (single connection, suitable for tests)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=echo,
            pool_pre_ping=pool_pre_ping,
        )
    elif "sqlite" in database_url:
        # SQLite with QueuePool (limited pooling support)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=QueuePool,
            pool_size=min(pool_size, 5),  # SQLite has limited concurrent access
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
        )
    else:
        # PostgreSQL/MySQL with full connection pooling
        engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
        )
    return engine


def create_pooled_sessionmaker(engine, autoflush: bool = False, autocommit: bool = False):
    """
    Create session factory with connection pooling.

    Args:
        engine: SQLAlchemy engine
        autoflush: Enable autoflush
        autocommit: Enable autocommit

    Returns:
        Session factory
    """
    return sessionmaker(bind=engine, autoflush=autoflush, autocommit=autocommit)


def create_async_pooled_engine(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    echo: bool = False,
):
    """
    Create async SQLAlchemy engine with connection pooling.

    Args:
        database_url: Database connection URL
        pool_size: Size of connection pool
        max_overflow: Maximum overflow connections
        pool_recycle: Connection recycle time in seconds
        pool_pre_ping: Test connections before using
        echo: Enable SQL query logging

    Returns:
        Async SQLAlchemy engine with connection pooling
    """
    # Convert to async URL
    if "sqlite" in database_url:
        async_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif "postgresql" in database_url:
        async_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_url = database_url

    engine = create_async_engine(
        async_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
        echo=echo,
    )
    return engine


def create_async_pooled_sessionmaker(engine, expire_on_commit: bool = False):
    """
    Create async session factory with connection pooling.

    Args:
        engine: Async SQLAlchemy engine
        expire_on_commit: Expire objects on commit

    Returns:
        Async session factory
    """
    return async_sessionmaker(engine, expire_on_commit=expire_on_commit)
