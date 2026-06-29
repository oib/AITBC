from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Load .env file
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

# Ensure pool-hub src is on the path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Set a default shared secret for test environments if not provided
os.environ.setdefault("POOLHUB_COORDINATOR_SHARED_SECRET", "test-secret")

# Import Base defensively — unit tests don't need it, only DB integration tests do
try:
    from poolhub.models import Base  # noqa: E402,F401
except Exception:  # pragma: no cover — only fails if settings/env misconfigured
    Base = None  # type: ignore[assignment]


def _get_required_env(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"Set {name} to run Pool Hub integration tests")
    return value


@pytest_asyncio.fixture()
async def db_engine() -> AsyncEngine:
    if Base is None:
        pytest.skip("poolhub.models not available — settings/env not configured")
    dsn = _get_required_env("POOLHUB_TEST_POSTGRES_DSN")
    engine = create_async_engine(dsn, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncSession:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def redis_client() -> Redis:
    redis_url = _get_required_env("POOLHUB_TEST_REDIS_URL")
    client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.close()


@pytest_asyncio.fixture(autouse=True)
async def _clear_redis(request: pytest.FixtureRequest) -> None:
    # Only clear Redis if the test actually uses redis_client
    if "redis_client" in request.fixturenames:
        redis_client = request.getfixturevalue("redis_client")
        await redis_client.flushdb()
