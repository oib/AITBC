"""MatchRepository persistence + Redis fan-out tests.

Drives the repository against a real async SQLite session (same convention as
test_sla_collector.py — the models' PGUUID/JSON/Numeric columns all map onto
SQLite types) plus an in-memory FakeRedis, so the publish path is exercised
without network or a real Redis.

Pins #1394 (POOLHUB-SERIAL-1): MatchResult.price is Numeric -> Decimal, and the
publish payload hands it to json.dumps raw, so every match with candidates dies
with TypeError after the DB commit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.models import Base, MatchRequest, MatchResult
from poolhub.repositories.match_repository import MatchRepository


class FakeRedis:
    """Minimal async Redis stand-in recording list/hash/zset/pubsub writes."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.published: list[tuple[str, str]] = []
        self.expirations: dict[str, int] = {}
        self.deleted: list[str] = []

    async def rpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        bucket = self.lists.get(key)
        if bucket is None:
            return True
        n = len(bucket)
        # Redis semantics: negative indexes count from the tail; stop=-1 is the
        # last element. Only the -N..-1 form is exercised by the repository.
        lo = max(start + n, 0) if start < 0 else min(start, n)
        hi = min(stop + n, n - 1) if stop < 0 else min(stop, n - 1)
        self.lists[key] = bucket[lo : hi + 1] if hi >= lo else []
        return True

    async def delete(self, key: str) -> int:
        self.deleted.append(key)
        self.lists.pop(key, None)
        return 1

    async def expire(self, key: str, ttl: int) -> bool:
        self.expirations[key] = ttl
        return True

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def hset(self, key: str, mapping: dict[str, str] | None = None) -> int:
        self.hashes[key] = dict(mapping or {})
        return len(self.hashes[key])

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.sorted_sets.setdefault(key, {}).update(mapping)
        return len(mapping)


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


async def _make_request(repo: MatchRepository, job_id: str = "job-1") -> MatchRequest:
    return await repo.create_request(job_id=job_id, requirements={"min_vram_gb": 8}, top_k=3)


class TestCreateRequest:
    async def test_enqueues_json_payload(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo)

        assert request.job_id == "job-1"
        assert request.top_k == 3
        queued = redis.lists["poolhub:match-requests"]
        assert len(queued) == 1
        payload = json.loads(queued[0])
        assert payload["job_id"] == "job-1"
        assert payload["request_id"] == str(request.id)
        assert payload["top_k"] == 3

    async def test_enqueue_trims_list_to_bound(self, session_factory, redis, monkeypatch):
        """#1531: the write-only match-requests list must stay bounded."""
        import poolhub.repositories.match_repository as match_repo_mod

        monkeypatch.setattr(match_repo_mod, "_MATCH_REQUESTS_MAX", 3)

        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            for i in range(6):
                await repo.create_request(job_id=f"job-{i}", requirements={}, enqueue=True)

        queued = redis.lists["poolhub:match-requests"]
        assert len(queued) == 3
        # Newest entries survive (rpush tail), oldest are trimmed from the head.
        assert [json.loads(q)["job_id"] for q in queued] == ["job-3", "job-4", "job-5"]

    async def test_enqueue_false_skips_redis(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            await repo.create_request(job_id="job-2", requirements={}, enqueue=False)

        assert "poolhub:match-requests" not in redis.lists


class TestAddResults:
    async def test_results_persisted(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo)
            results = await repo.add_results(
                request_id=UUID(str(request.id)),
                candidates=[{"miner_id": "m-1", "score": 0.9, "eta_ms": 120, "price": None}],
            )

        assert len(results) == 1
        assert results[0].miner_id == "m-1"
        assert results[0].score == 0.9

    async def test_published_payloads_are_json_serializable(self, session_factory, redis):
        """Every payload pushed to Redis must round-trip through json.

        #1394: ``price`` is a Decimal straight off Numeric(20,8); json.dumps
        raises TypeError, so /v1/match 500s after committing the rows.
        """
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo)
            await repo.add_results(
                request_id=UUID(str(request.id)),
                candidates=[
                    {
                        "miner_id": "m-1",
                        "score": 0.9,
                        "eta_ms": 120,
                        "price": Decimal("0.01000000"),
                        "explain": "score=0.900",
                    }
                ],
            )

        channel, raw = redis.published[0]
        assert channel == "poolhub:events:match-results:job-1"
        payload = json.loads(raw)  # raises today: Decimal is not JSON serializable
        assert payload["miner_id"] == "m-1"
        assert payload["price"] is not None

    async def test_no_candidates_publishes_nothing(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo)
            await repo.add_results(request_id=UUID(str(request.id)), candidates=[])

        # The stale-results key is cleared even with zero candidates — that is
        # correct cache semantics; what must not happen is a publish.
        assert redis.published == []
        assert redis.deleted == ["poolhub:match-results:job-1"]

    async def test_publish_false_skips_redis(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo)
            await repo.add_results(
                request_id=UUID(str(request.id)),
                candidates=[{"miner_id": "m-1", "score": 0.5, "price": None}],
                publish=False,
            )

        assert redis.published == []


class TestListing:
    async def test_list_recent_requests_respects_limit(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            for i in range(5):
                await repo.create_request(job_id=f"job-{i}", requirements={}, enqueue=False)
            recent = await repo.list_recent_requests(limit=2)

        assert len(recent) == 2

    async def test_list_results_for_job_respects_limit(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo, job_id="job-x")
            for i in range(4):
                await repo.add_results(
                    request_id=UUID(str(request.id)),
                    candidates=[{"miner_id": f"m-{i}", "score": float(i), "price": None}],
                    publish=False,
                )
            results = await repo.list_results_for_job("job-x", limit=3)

        assert len(results) == 3

    async def test_list_results_for_other_job_is_empty(self, session_factory, redis):
        async with session_factory() as s:
            repo = MatchRepository(s, redis)
            request = await _make_request(repo, job_id="job-a")
            await repo.add_results(
                request_id=UUID(str(request.id)),
                candidates=[{"miner_id": "m-1", "score": 0.5, "price": None}],
                publish=False,
            )
            assert await repo.list_results_for_job("job-b") == []


class TestResultPayload:
    def test_payload_serializes_datetimes(self):
        """_result_payload output must be JSON-safe for every field it emits."""
        result = MatchResult(
            request_id=UUID(int=0),
            miner_id="m-1",
            score=0.5,
            explain=None,
            eta_ms=None,
            price=None,
            created_at=datetime.now(UTC),
        )
        repo = MatchRepository(session=None, redis=None)  # type: ignore[arg-type]
        payload = repo._result_payload(result)
        json.dumps(payload)  # must not raise
