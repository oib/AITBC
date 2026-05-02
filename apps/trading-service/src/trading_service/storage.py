"""
Database session management for Trading service
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from aitbc import get_logger

logger = get_logger(__name__)

# Database URL from environment variable or default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/trading_service.db")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)


async def init_db() -> None:
    """Initialize database tables"""
    from .domain.trading import (
        TradeRequest,
        TradeMatch,
        TradeNegotiation,
        TradeAgreement,
        TradeSettlement,
        TradeFeedback,
        TradingAnalytics,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    logger.info("Trading service database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
