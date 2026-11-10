"""#1532 pins: ollama_queue must share one Redis client per process.

Pre-fix: ``_redis()`` built a fresh ``Redis.from_url`` per call and
``get_queue()`` is invoked per ``POST /tasks/ollama`` request — each request
leaked a client (and its connection pool) because nothing closed it.
"""

from __future__ import annotations

import json

import pytest

from coordinator_api.contexts.market.services import ollama_queue
from coordinator_api.contexts.market.services.ollama_queue import OllamaQueue, aclose_redis, get_queue


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def made_clients(monkeypatch: pytest.MonkeyPatch) -> list[_FakeRedis]:
    clients: list[_FakeRedis] = []

    def _from_url(*args: object, **kwargs: object) -> _FakeRedis:
        client = _FakeRedis()
        clients.append(client)
        return client

    # ollama_queue.Redis IS redis.asyncio.Redis; patch the classmethod the
    # module calls (the test conftest points settings.redis.url at sqlite,
    # which from_url rejects — the URL value is irrelevant here).
    monkeypatch.setattr(ollama_queue.Redis, "from_url", staticmethod(_from_url))
    return clients


async def test_get_queue_reuses_shared_client(made_clients: list[_FakeRedis]) -> None:
    await aclose_redis()
    try:
        q1 = await get_queue()
        q2 = await get_queue()
        assert isinstance(q1, OllamaQueue)
        assert q1.redis is q2.redis
        assert len(made_clients) == 1
    finally:
        await aclose_redis()


async def test_aclose_redis_resets_client(made_clients: list[_FakeRedis]) -> None:
    await aclose_redis()
    try:
        q1 = await get_queue()
        await aclose_redis()
        assert made_clients[0].closed
        q2 = await get_queue()
        assert q1.redis is not q2.redis
        assert len(made_clients) == 2
    finally:
        await aclose_redis()


class _ListRedis:
    """Minimal async Redis list stand-in with real LPUSH/LTRIM/BRPOP semantics."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def lpush(self, key: str, value: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.insert(0, value)
        return len(bucket)

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        bucket = self.lists.get(key)
        if bucket is None:
            return True
        n = len(bucket)
        lo = max(start + n, 0) if start < 0 else min(start, n)
        hi = min(stop + n, n - 1) if stop < 0 else min(stop, n - 1)
        self.lists[key] = bucket[lo : hi + 1] if hi >= lo else []
        return True

    async def brpop(self, key: str, timeout: float = 0):
        bucket = self.lists.get(key) or []
        if not bucket:
            return None
        # BRPOP consumes from the tail = oldest entry.
        return (key, bucket.pop())


async def test_enqueue_trims_queue_to_max_length() -> None:
    """#1532: lpush is followed by LTRIM so a dead worker cannot grow the
    queue forever; the newest QUEUE_MAX_LENGTH tasks survive, oldest drop."""
    from coordinator_api.contexts.market.services.ollama_queue import QUEUE_KEY, QUEUE_MAX_LENGTH

    redis = _ListRedis()
    # Fill beyond the cap, then enqueue one more.
    for i in range(QUEUE_MAX_LENGTH + 5):
        await redis.lpush(QUEUE_KEY, json.dumps({"task_id": f"old-{i}", "prompt": "p"}))
    await redis.ltrim(QUEUE_KEY, 0, QUEUE_MAX_LENGTH - 1)

    q = OllamaQueue(redis)  # type: ignore[arg-type]
    task_id = await q.enqueue(gpu_id="g1", model="m", prompt="p")

    bucket = redis.lists[QUEUE_KEY]
    assert len(bucket) == QUEUE_MAX_LENGTH
    # Newest (just-enqueued) task is at the head; oldest entries dropped.
    assert json.loads(bucket[0])["task_id"] == task_id
    # BRPOP still yields the oldest surviving task first (FIFO preserved).
    oldest = await q.dequeue(timeout=0)
    assert oldest is not None
    assert oldest["task_id"] != task_id
