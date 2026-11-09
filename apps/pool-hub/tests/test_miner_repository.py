"""MinerRepository tests — registration, status updates, Redis sync, scoring.

#1399 (POOLHUB-INPUT-1): miner-reported numerics are stored unvalidated —
negative queue_len inflates _compute_score above its theoretical maximum and
negative latency flows into MatchResult.eta_ms / SLA response-time metrics.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.app.routers.miners import MinerHeartbeatRequest
from poolhub.models import Base, Miner, MinerStatus
from poolhub.repositories.miner_repository import MinerRepository
from poolhub.settings import settings


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.expirations: dict[str, int] = {}

    async def hset(self, key: str, mapping: dict[str, str] | None = None) -> int:
        self.hashes[key] = dict(mapping or {})
        return len(self.hashes[key])

    async def expire(self, key: str, ttl: int) -> bool:
        self.expirations[key] = ttl
        return True

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.sorted_sets.setdefault(key, {}).update(mapping)
        return len(mapping)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


def _register_kwargs(**overrides) -> dict:
    kwargs = {
        "miner_id": "m-1",
        "api_key_hash": "h" * 64,
        "addr": "/ip4/127.0.0.1/tcp/9000",
        "proto": "tcp",
        "gpu_vram_gb": 24.0,
        "gpu_name": "RTX 4090",
        "cpu_cores": 16,
        "ram_gb": 64.0,
        "max_parallel": 4,
        "base_price": Decimal("0.01"),
        "tags": {},
        "capabilities": ["whisper"],
        "region": "eu-1",
    }
    kwargs.update(overrides)
    return kwargs


class TestRegisterMiner:
    async def test_first_registration_creates_miner_and_status(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            miner = await repo.register_miner(**_register_kwargs())

        assert miner.miner_id == "m-1"
        async with db_session() as s:
            status = await s.get(MinerStatus, "m-1")
            assert status is not None

    async def test_reregistration_updates_fields(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.register_miner(**_register_kwargs())
            await repo.register_miner(**_register_kwargs(gpu_vram_gb=48.0, region="us-1"))

        async with db_session() as s:
            miner = await s.get(Miner, "m-1")
            assert miner.gpu_vram_gb == 48.0
            assert miner.region == "us-1"

    async def test_redis_hash_and_ranking_written(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.register_miner(**_register_kwargs())

        key = "poolhub:miner:m-1"
        assert key in redis.hashes
        payload = redis.hashes[key]
        assert payload["miner_id"] == "m-1"
        assert payload["gpu_vram_gb"] == "24.0"
        assert payload["base_price"] == "0.01"
        assert "poolhub:rankings:eu-1" in redis.sorted_sets
        assert "m-1" in redis.sorted_sets["poolhub:rankings:eu-1"]
        assert redis.expirations[key] == settings.session_ttl_seconds + settings.heartbeat_grace_seconds


class TestUpdateStatus:
    async def test_only_provided_fields_update(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.register_miner(**_register_kwargs())
            await repo.update_status("m-1", queue_len=3, busy=True)

        async with db_session() as s:
            status = await s.get(MinerStatus, "m-1")
            assert status.queue_len == 3
            assert status.busy is True
            assert status.avg_latency_ms is None

    async def test_unknown_miner_is_noop(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.update_status("ghost", queue_len=1)  # must not raise


class TestTouchHeartbeat:
    async def test_stamps_last_heartbeat_at(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.register_miner(**_register_kwargs())
            await repo.touch_heartbeat("m-1")

        async with db_session() as s:
            status = await s.get(MinerStatus, "m-1")
            assert status.last_heartbeat_at is not None
            # SQLite drops tzinfo on DateTime(timezone=True) round-trips
            # (see _as_utc in sla_collector.py) — Postgres preserves it.
            miner = await s.get(Miner, "m-1")
            assert miner.last_seen_at is not None

    async def test_unknown_miner_is_noop(self, db_session, redis):
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.touch_heartbeat("ghost")


class TestComputeScore:
    @pytest.fixture
    def repo(self):
        return MinerRepository(session=None, redis=None)  # type: ignore[arg-type]

    def _miner_ns(self, **overrides):
        base = {
            "max_parallel": 4,
            "base_price": Decimal("0.01"),
            "trust_score": 0.5,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_idle_miner_scores_high(self, repo):
        score = repo._compute_score(self._miner_ns(), SimpleNamespace(queue_len=0))
        w = settings.default_score_weights
        expected = w.capability + w.price + w.load + w.trust * 0.5
        assert score == pytest.approx(expected)

    def test_fully_loaded_miner_scores_lower(self, repo):
        idle = repo._compute_score(self._miner_ns(), SimpleNamespace(queue_len=0))
        busy = repo._compute_score(self._miner_ns(), SimpleNamespace(queue_len=4))
        assert busy < idle

    def test_missing_status_treated_as_idle(self, repo):
        score = repo._compute_score(self._miner_ns(), None)
        assert score > 0

    @pytest.mark.xfail(
        strict=True,
        reason="negative queue_len → utilization<0 → load_factor>1 → score above theoretical max; fix tracked in #1399",
    )
    def test_negative_queue_len_cannot_inflate_score(self, repo):
        """Weights sum to 1.0, so no legitimate state may exceed this bound."""
        w = settings.default_score_weights
        max_legit = w.capability + w.price + w.load + w.trust  # trust_score<=1
        miner = self._miner_ns(trust_score=1.0)
        score = repo._compute_score(miner, SimpleNamespace(queue_len=-10))
        assert score <= max_legit


class TestHeartbeatInputValidation:
    """#1399: the heartbeat schema accepts negatives today — pinned as xfail."""

    @pytest.mark.xfail(
        strict=True,
        reason="MinerHeartbeatRequest has no ge=0 bounds — negative jobs/latency are accepted and stored; fix tracked in #1399",
    )
    def test_heartbeat_schema_bounds_numerics(self):
        # Documents the intended contract: non-negative counters only.
        with pytest.raises(ValidationError):
            MinerHeartbeatRequest(current_jobs=-5, network_latency_ms=-1.0, memory_used=-100)

    @pytest.mark.xfail(
        strict=True,
        reason="update_status persists negative queue_len/avg_latency_ms reported by the miner; fix tracked in #1399",
    )
    async def test_update_status_stores_only_sane_values(self, db_session, redis):
        """Negative queue_len/latency must not reach MinerStatus."""
        async with db_session() as s:
            repo = MinerRepository(s, redis)
            await repo.register_miner(**_register_kwargs())
            await repo.update_status("m-1", queue_len=-5, avg_latency_ms=-100)

        async with db_session() as s:
            status = await s.get(MinerStatus, "m-1")
            assert status.queue_len >= 0
            assert (status.avg_latency_ms or 0) >= 0
