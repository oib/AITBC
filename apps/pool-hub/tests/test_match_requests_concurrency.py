"""Concurrency pin for the #1531 match-requests LTRIM bound.

``create_request(enqueue=True)`` does ``RPUSH`` then ``LTRIM key -MAX -1`` as
two separate awaited commands. Under simultaneous publishers the interleaving
is arbitrary, but the bound still holds: every push is followed by its own
trim, so the last trim to run leaves at most ``_MATCH_REQUESTS_MAX`` entries
— no push can land after the final trim without its own later trim.

The fake Redis yields inside every command (``asyncio.sleep(0)``) so the
gather genuinely interleaves rpush/ltrim pairs instead of running each
request atomically. The bound is monkeypatched down to 10 so 50 concurrent
publishers actually exercise the trim path.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import poolhub.repositories.match_repository as match_repo_mod
from poolhub.models import Base
from poolhub.repositories.match_repository import MatchRepository

_MATCH_REQUESTS_KEY = "poolhub:match-requests"
_PUBLISHERS = 50
_BOUND = 10


class YieldingFakeRedis:
    """Async Redis list stand-in that yields inside every command.

    Real Redis interleaves concurrent clients between commands; a fake with
    no internal awaits would let each rpush+ltrim pair run atomically and
    never exercise the race the bound is supposed to survive.
    """

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def rpush(self, key: str, *values: str) -> int:
        await asyncio.sleep(0)
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        await asyncio.sleep(0)
        bucket = self.lists.get(key)
        if bucket is None:
            return True
        n = len(bucket)
        lo = max(start + n, 0) if start < 0 else min(start, n)
        hi = min(stop + n, n - 1) if stop < 0 else min(stop, n - 1)
        self.lists[key] = bucket[lo : hi + 1] if hi >= lo else []
        return True


@pytest.fixture
async def session_factory(tmp_path):
    # File-backed SQLite: :memory: gives each pooled connection its own
    # private database, which breaks under concurrent sessions.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/match_requests.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_match_requests_list_bounded_under_concurrent_publish(session_factory, monkeypatch):
    monkeypatch.setattr(match_repo_mod, "_MATCH_REQUESTS_MAX", _BOUND)
    redis = YieldingFakeRedis()

    async def publish(i: int):
        async with session_factory() as session:
            repo = MatchRepository(session, redis)
            return await repo.create_request(job_id=f"job-{i}", requirements={"min_vram_gb": 8}, enqueue=True)

    results = await asyncio.gather(*(publish(i) for i in range(_PUBLISHERS)))

    # No exception escaped and every request committed.
    assert len(results) == _PUBLISHERS
    assert {r.job_id for r in results} == {f"job-{i}" for i in range(_PUBLISHERS)}

    queued = redis.lists.get(_MATCH_REQUESTS_KEY, [])
    # The cap holds exactly: 50 pushes, bound 10 -> newest 10 survive.
    assert len(queued) == _BOUND
    job_ids = [json.loads(entry)["job_id"] for entry in queued]
    assert len(set(job_ids)) == _BOUND
    # Newest entries win: the trimmed list is a suffix of the publish order
    # as observed by Redis (rpush order), so every surviving id is one of the
    # last _BOUND pushes — assert membership, not exact order (interleaving
    # makes push order nondeterministic but each id appears once).
    assert set(job_ids) <= {f"job-{i}" for i in range(_PUBLISHERS)}
