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

# Database URL from environment variable or default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/marketplace_service.db")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)

logger.info(f"Storage module loaded: engine={engine}, DATABASE_URL={DATABASE_URL}")


async def init_db() -> None:
    """Initialize database tables"""

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("Marketplace service database initialized")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    try:
        logger.debug(f"Creating database session, engine={engine}, id={id(engine)}")
        AsyncSessionClass = AsyncSession
        logger.debug(f"AsyncSession class: {AsyncSessionClass}, callable: {callable(AsyncSessionClass)}")
        session = AsyncSessionClass(engine)
        logger.debug(f"Session created: {session}")
        async with session:
            logger.debug("Database session yielded")
            yield session
            logger.debug("Database session closed")
    except Exception as e:
        logger.error(f"Error in get_session: {type(e).__name__}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


@asynccontextmanager
async def get_session_context() -> AsyncIterator[AsyncSession]:
    """Get database session as context manager"""
    async with AsyncSession(engine) as session:
        yield session
