"""#1532 pins: ollama_queue must share one Redis client per process.

Pre-fix: ``_redis()`` built a fresh ``Redis.from_url`` per call and
``get_queue()`` is invoked per ``POST /tasks/ollama`` request — each request
leaked a client (and its connection pool) because nothing closed it.
"""

from __future__ import annotations

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
