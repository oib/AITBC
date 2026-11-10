"""#1534 pins: GossipClient Redis subscription cleanup.

Pre-fix: ``_listen`` only ran ``pubsub.unsubscribe()``/``sub_redis.aclose()``
after the ``pubsub.listen()`` loop exited normally. ``GossipSubscription.close()``
cancels the listener task, the ``except asyncio.CancelledError`` swallowed the
cancellation, and the dedicated Redis connection plus its server-side SUBSCRIBE
leaked for the process lifetime.
"""

from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis

from trading_service.services.gossip_client import GossipClient


class _FakePubSub:
    def __init__(self) -> None:
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, topic: str) -> None:
        pass

    async def unsubscribe(self, topic: str) -> None:
        self.unsubscribed.append(topic)

    async def aclose(self) -> None:
        self.closed = True

    def listen(self):
        async def _gen():
            # Never yields: the subscription stays open until cancelled.
            while True:
                await asyncio.sleep(3600)
                yield  # pragma: no cover

        return _gen()


class _FakeRedis:
    """Stand-in for redis.asyncio.Redis covering ping/pubsub/aclose."""

    instances: list[_FakeRedis] = []

    def __init__(self) -> None:
        self.pubsubs: list[_FakePubSub] = []
        self.closed = False
        _FakeRedis.instances.append(self)

    async def ping(self) -> bool:
        return True

    def pubsub(self) -> _FakePubSub:
        ps = _FakePubSub()
        self.pubsubs.append(ps)
        return ps

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> type[_FakeRedis]:
    _FakeRedis.instances.clear()

    def _from_url(*args: object, **kwargs: object) -> _FakeRedis:
        return _FakeRedis()

    monkeypatch.setattr(aioredis.Redis, "from_url", staticmethod(_from_url))
    return _FakeRedis


async def test_close_releases_pubsub_and_connection(fake_redis: type[_FakeRedis]) -> None:
    client = GossipClient(backend="broadcast", redis_url="redis://localhost:6379")
    await client.start()
    assert client.using_redis

    sub = await client.subscribe("offers.chain-a")
    # Let the listener task reach pubsub.listen().
    for _ in range(10):
        await asyncio.sleep(0)

    sub.close()
    # _close only schedules the cancel; give the listener a few loop turns.
    for _ in range(20):
        await asyncio.sleep(0)
        if _FakeRedis.instances and _FakeRedis.instances[-1].closed:
            break

    listener = _FakeRedis.instances[-1]
    assert listener.pubsubs, "listener never opened a pubsub"
    pubsub = listener.pubsubs[0]
    assert pubsub.unsubscribed == ["offers.chain-a"]
    assert pubsub.closed
    assert listener.closed

    await client.stop()
