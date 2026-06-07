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

# Database configuration
DB_TYPE = os.getenv("DB_TYPE", "sqlite")  # or "postgresql"
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "aitbc_governance")
DB_USER = os.getenv("DB_USER", "aitbc")
DB_PASS = os.getenv("DB_PASS", "")

# Build database URL based on type
if DB_TYPE == "postgresql":
    DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # FHS-compliant path for SQLite
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////var/lib/aitbc/data/governance_service.db")

# Create async engine with connection pooling
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)


async def init_db() -> None:
    """Initialize database tables"""

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("Governance service database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
