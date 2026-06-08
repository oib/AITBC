"""
Database session management for Governance service
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from aitbc import get_logger

logger = get_logger(__name__)

def _build_database_url() -> str:
    """Build database URL from environment variables at call time."""
    db_type = os.getenv("DB_TYPE", "sqlite")
    if db_type == "postgresql":
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "aitbc_governance")
        user = os.getenv("DB_USER", "aitbc")
        password = os.getenv("DB_PASS", "")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
    return os.getenv("DATABASE_URL", "sqlite+aiosqlite:////var/lib/aitbc/data/governance_service.db")


def _create_engine():
    """Create async engine based on current environment."""
    db_type = os.getenv("DB_TYPE", "sqlite")
    url = _build_database_url()
    kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if db_type == "postgresql":
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return create_async_engine(url, **kwargs)


engine = _create_engine()


async def init_db() -> None:
    """Initialize database tables.

    For PostgreSQL, Alembic manages schema migrations so we skip create_all.
    For SQLite (dev/test), create tables automatically.
    """
    if os.getenv("DB_TYPE", "sqlite") != "postgresql":
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("Governance service database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
