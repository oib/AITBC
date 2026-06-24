"""Database session management for Edge API Service"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from aitbc.aitbc_logging import get_logger

from .config import settings

logger = get_logger(__name__)


def _get_async_db_url() -> str:
    """Get the async-compatible database URL from settings."""
    url: str = settings.database.effective_url
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _get_async_db_url()
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "").split("?")[0]
    db_dir = os.path.dirname(db_path)
    if db_dir and (not os.path.exists(db_dir)):
        os.makedirs(db_dir, exist_ok=True)
        logger.info("Created database directory: %s", db_dir)
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600)


async def init_db() -> None:
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Edge API database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
