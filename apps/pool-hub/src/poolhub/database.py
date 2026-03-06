from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .settings import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            settings.postgres_dsn,
            pool_size=settings.postgres_pool_max,
            max_overflow=0,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        create_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def close_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None

