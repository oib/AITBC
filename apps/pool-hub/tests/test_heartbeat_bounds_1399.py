"""#1399 POOLHUB-INPUT-1 / #1402 flag: miner-reported numerics are bounded.

Schema bounds (422), repository clamps behind them, score floor, and the
response-time metric being labelled as miner-self-reported.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from poolhub.app.routers.miners import MinerHeartbeatRequest
from poolhub.models import Base, MinerStatus
from poolhub.repositories.miner_repository import MinerRepository
from poolhub.settings import settings
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class _Redis:
    async def hset(self, key, mapping=None):
        return 1

    async def expire(self, key, ttl):
        return True

    async def zadd(self, key, mapping):
        return 1


@pytest_asyncio.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_jobs", -5),
        ("current_jobs", 10**9),
        ("gpu_utilization", -1),
        ("gpu_utilization", 101),
        ("memory_used", -100),
        ("memory_total", -1),
        ("network_latency_ms", -1.0),
        ("network_latency_ms", float("inf")),
        ("network_latency_ms", float("nan")),
        ("network_latency_ms", 10**9),
    ],
)
def test_heartbeat_schema_rejects_bad_numerics(field, value):
    with pytest.raises(ValidationError):
        MinerHeartbeatRequest(**{field: value})


def test_heartbeat_schema_accepts_sane_values():
    hb = MinerHeartbeatRequest(current_jobs=3, gpu_utilization=100, memory_used=1, memory_total=2, network_latency_ms=0.0)
    assert hb.current_jobs == 3 and hb.network_latency_ms == 0.0


@pytest.mark.parametrize("queue_len", [-1, -10, -(10**6)])
def test_negative_queue_len_cannot_inflate_score(queue_len):
    repo = MinerRepository.__new__(MinerRepository)
    w = settings.default_score_weights
    max_legit = w.capability + w.price + w.load + w.trust
    miner = SimpleNamespace(max_parallel=4, base_price=Decimal("0.01"), trust_score=1.0)
    assert repo._compute_score(miner, SimpleNamespace(queue_len=queue_len)) <= max_legit + 1e-9
    idle = repo._compute_score(miner, SimpleNamespace(queue_len=0))
    assert repo._compute_score(miner, SimpleNamespace(queue_len=queue_len)) == pytest.approx(idle)


@pytest.mark.asyncio
async def test_update_status_clamps_negative_values(maker):
    async with maker() as s:
        repo = MinerRepository(s, _Redis())
        await repo.register_miner(
            miner_id="m-1",
            api_key_hash="h" * 64,
            addr="127.0.0.1:1",
            proto="http",
            gpu_vram_gb=8,
            gpu_name="x",
            cpu_cores=4,
            ram_gb=16,
            max_parallel=2,
            base_price=Decimal("0.01"),
            tags={},
            capabilities=[],
            region=None,
        )
        await repo.update_status("m-1", queue_len=-5, avg_latency_ms=-100, mem_free_gb=-3.0)
    async with maker() as s:
        status = await s.get(MinerStatus, "m-1")
        assert status.queue_len == 0
        assert status.avg_latency_ms == 0
        assert status.mem_free_gb == 0.0
