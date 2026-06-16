"""
Database session management for Marketplace service
"""

import os
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from aitbc import get_logger

logger = get_logger(__name__)
DATABASE_URL = os.getenv(
    "MARKETPLACE_DATABASE_URL", os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/marketplace_service.db")
)
engine = create_async_engine(DATABASE_URL, echo=False)
logger.info("Storage module loaded: engine=%s, DATABASE_URL=%s", engine, os.getenv("MARKETPLACE_DATABASE_URL", "not set"))


async def init_db() -> None:
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Marketplace service database initialized")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    try:
        logger.debug("Creating database session, engine=%s, id=%s", engine, id(engine))
        AsyncSessionClass = AsyncSession
        logger.debug("AsyncSession class: %s, callable: %s", AsyncSessionClass, callable(AsyncSessionClass))
        session = AsyncSessionClass(engine, expire_on_commit=False)
        logger.debug("Session created: %s", session)
        async with session:
            logger.debug("Database session yielded")
            yield session
            logger.debug("Database session closed")
    except Exception as e:
        logger.error("Error in get_session: %s: %s", type(e).__name__, str(e))
        logger.error("Traceback: %s", traceback.format_exc())
        raise


@asynccontextmanager
async def get_session_context() -> AsyncIterator[AsyncSession]:
    """Get database session as context manager"""
    async with AsyncSession(engine) as session:
        yield session
