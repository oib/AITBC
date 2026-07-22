"""
Database session management for Trading service
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

logger = get_logger(__name__)

# Database URL from environment variable or default
DEFAULT_DB = f"sqlite+aiosqlite:///{DATA_DIR}/data/trading_service.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB)

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)


async def init_db() -> None:
    """Initialize database engine.

    Schema management is Alembic's job. Do not call create_all() here.
    Run `alembic upgrade head` before service startup.
    """
    # Ensure the engine is ready; migrations must be applied externally.
    logger.info("Trading service database engine ready (migrations managed by Alembic)")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
