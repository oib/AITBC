"""
Database session management for GPU service
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

# Importing the models is what puts them on `gpu_metadata`; create_all builds nothing
# otherwise. This service's tables live there rather than on the global SQLModel registry --
# see domain/base.py (V23-72).
from .domain import gpu_marketplace as _models  # noqa: F401
from .domain.base import gpu_metadata

logger = get_logger(__name__)

# Database URL from environment variable or default
DEFAULT_DB = f"sqlite+aiosqlite:///{DATA_DIR}/data/gpu_service.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB)

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)


async def init_db() -> None:
    """Initialize database tables"""

    async with engine.begin() as conn:
        await conn.run_sync(gpu_metadata.create_all)

    logger.info("GPU service database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
