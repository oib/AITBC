"""Pin for #1554: dead-miner freshness filter in list_active_miners.

Postgres miner/miner_status rows never expire — without a freshness window a
miner that stopped heartbeating stayed matchable forever.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.models import Base, Miner, MinerStatus
from poolhub.repositories.miner_repository import MinerRepository


class FakeRedis:
    async def hset(self, *a, **k):
        return 0

    async def expire(self, *a, **k):
        return True

    async def zadd(self, *a, **k):
        return 0


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _miner(miner_id: str, **overrides) -> Miner:
    kwargs = {
        "miner_id": miner_id,
        "api_key_hash": "h" * 64,
        "addr": "/ip4/127.0.0.1/tcp/9000",
        "proto": "tcp",
        "gpu_vram_gb": 24.0,
        "cpu_cores": 16,
        "ram_gb": 64.0,
        "max_parallel": 4,
        "base_price": Decimal("0.01"),
    }
    kwargs.update(overrides)
    return Miner(**kwargs)


class TestActiveMinerFreshness:
    @pytest.mark.asyncio
    async def test_stale_heartbeat_excluded(self, db_session):
        async with db_session() as s:
            repo = MinerRepository(s, FakeRedis())
            fresh = _miner("fresh", last_seen_at=dt.datetime.now(dt.UTC))
            stale = _miner("stale", last_seen_at=dt.datetime.now(dt.UTC) - dt.timedelta(hours=2))
            s.add_all([fresh, stale])
            await s.commit()
            miners = await repo.list_active_miners()
            ids = {m.miner_id for m, _status, _score in miners}
            assert ids == {"fresh"}

    @pytest.mark.asyncio
    async def test_no_contact_excluded(self, db_session):
        async with db_session() as s:
            repo = MinerRepository(s, FakeRedis())
            s.add(_miner("ghost"))  # last_seen_at NULL — never checked in
            await s.commit()
            miners = await repo.list_active_miners()
            assert miners == []

    @pytest.mark.asyncio
    async def test_recent_heartbeat_counts_as_contact(self, db_session):
        async with db_session() as s:
            repo = MinerRepository(s, FakeRedis())
            miner = _miner("m-1", last_seen_at=dt.datetime.now(dt.UTC) - dt.timedelta(hours=2))
            s.add(miner)
            await s.flush()
            s.add(
                MinerStatus(
                    miner_id="m-1",
                    last_heartbeat_at=dt.datetime.now(dt.UTC),
                )
            )
            await s.commit()
            miners = await repo.list_active_miners()
            assert {m.miner_id for m, _s, _sc in miners} == {"m-1"}
