"""Database session management for Edge API Service"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from aitbc import get_logger

logger = get_logger(__name__)

# Database URL from environment variable or default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///var/lib/aitbc/data/edge.db")

# Ensure data directory exists
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "").split("?")[0]
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")

# Create async engine with proper connection pool settings
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
)


async def init_db() -> None:
    """Initialize database tables"""
    from .schemas.island import IslandMembership, BridgeRequest
    from .schemas.gpu import GPUListing
    from .schemas.database import EdgeDatabase
    from .schemas.serve import ComputeRequest, ComputeResult
    from .schemas.metrics import EdgeMetrics
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    logger.info("Edge API database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
