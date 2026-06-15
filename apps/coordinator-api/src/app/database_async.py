"""Async database module with connection pooling for Coordinator API."""
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

logger = logging.getLogger(__name__)
_async_engine = None
_async_session_factory = None

def _build_async_url(url: str) -> str:
    """Convert sync database URL to async URL.
    
    Examples:
        sqlite:///path.db -> sqlite+aiosqlite:///path.db
        postgresql://user:pass@host/db -> postgresql+asyncpg://user:pass@host/db
    """
    if '?' in url:
        base, params = url.split('?', 1)
        if base.startswith('sqlite:'):
            return f'{base}+aiosqlite://?{params}'
        elif base.startswith('postgresql:'):
            return f'{base}+asyncpg://?{params}'
        else:
            return f'{base}+aiosqlite://?{params}'
    elif url.startswith('sqlite:'):
        return url.replace('sqlite:', 'sqlite+aiosqlite:')
    elif url.startswith('postgresql:'):
        return url.replace('postgresql:', 'postgresql+asyncpg:')
    else:
        return url.replace(':', '+aiosqlite:')

def init_async_db() -> None:
    """Initialize async database engine and session factory."""
    global _async_engine, _async_session_factory
    try:
        sync_url = str(settings.database.effective_url)
        async_url = _build_async_url(sync_url)
        logger.info('Initializing async database connection: %s://...', async_url.split('://')[0])
        _async_engine = create_async_engine(async_url, echo=settings.database.echo if hasattr(settings.database, 'echo') else False, pool_size=getattr(settings.database, 'pool_size', 5), max_overflow=getattr(settings.database, 'max_overflow', 10), pool_pre_ping=getattr(settings.database, 'pool_pre_ping', True), pool_recycle=getattr(settings.database, 'pool_recycle', 3600))
        _async_session_factory = sessionmaker(_async_engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]
        logger.info('Async database initialized successfully')
    except Exception as e:
        logger.error('Failed to initialize async database: %s', e)
        raise

def get_async_db() -> AsyncSession:
    """Dependency to get async database session.
    
    Yields:
        AsyncSession: Database session that closes automatically
    """
    if _async_session_factory is None:
        raise RuntimeError('Async database not initialized. Call init_async_db() first.')

    async def _get_async_db() -> AsyncSession:  # type: ignore[misc]
        async with _async_session_factory() as session:
            try:
                yield session
            finally:
                await session.close()
    return _get_async_db()

def get_sync_engine() -> Any:
    """Get synchronous engine for backward compatibility.
    
    Returns:
        Engine: SQLAlchemy synchronous engine
    """
    from .database import engine
    return engine

async def close_async_db() -> None:
    """Close async database connections."""
    global _async_engine, _async_session_factory
    if _async_engine is not None:
        logger.info('Closing async database connections...')
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info('Async database connections closed')
