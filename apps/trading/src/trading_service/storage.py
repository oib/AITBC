"""
Database session management for Trading service
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR
from aitbc.database.target import resolve_service_database_url

logger = get_logger(__name__)

# Database URL: the same resolver the migrator uses (PG-TARGET-1) — DB_TYPE+DB_* win,
# then DATABASE_URL, then the sqlite default.
DEFAULT_DB = f"sqlite+aiosqlite:///{DATA_DIR}/data/trading_service.db"
DATABASE_URL = resolve_service_database_url(default_url=DEFAULT_DB, default_db_name="aitbc_trading")

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
