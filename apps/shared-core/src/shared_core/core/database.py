"""Shared database utilities for AITBC services."""

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DatabaseConfig

Base = declarative_base()


def get_engine(config: DatabaseConfig):
    """Create SQLAlchemy engine based on configuration."""
    if config.adapter == "sqlite":
        # SQLite needs special handling for async
        engine = create_engine(
            config.effective_url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_pre_ping=config.pool_pre_ping,
            echo=config.db_echo if hasattr(config, "db_echo") else False,
        )
        return engine
    else:
        return create_engine(
            config.effective_url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_pre_ping=config.pool_pre_ping,
            echo=config.db_echo if hasattr(config, "db_echo") else False,
        )


def get_sessionmaker(engine):
    """Create session factory."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Async support (for async services)
def get_async_engine(config: DatabaseConfig):
    """Create async SQLAlchemy engine."""
    if config.adapter == "sqlite":
        # SQLite async uses aiosqlite
        async_url = config.effective_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        return create_async_engine(async_url, echo=config.db_echo if hasattr(config, "db_echo") else False)
    else:
        # PostgreSQL async uses asyncpg
        async_url = config.effective_url.replace("postgresql://", "postgresql+asyncpg://")
        return create_async_engine(
            async_url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            echo=config.db_echo if hasattr(config, "db_echo") else False,
        )


async def get_async_session(engine) -> AsyncGenerator[AsyncSession]:
    """Dependency for FastAPI async endpoints."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
