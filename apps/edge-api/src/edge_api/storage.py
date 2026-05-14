"""Database session management for Edge API Service"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from aitbc import get_logger

logger = get_logger(__name__)

# Database URL from environment variable or default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://aitbc_edge:password@localhost:5432/aitbc_edge")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)


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
