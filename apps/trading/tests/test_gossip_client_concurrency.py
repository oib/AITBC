"""Concurrency pins for gossip_client subscription lifecycle (#1534).

Two bounded resources are hammered simultaneously:

* Redis path: N concurrent ``subscribe()`` calls each spawn a listener task
  holding a dedicated pub/sub connection; ``close()`` must release
  unsubscribe + aclose on EVERY listener — no leaked tasks or connections.
* In-memory fallback: subscriber queues are bounded (``max_queue_size``) and
  ``publish_local`` drops on full instead of raising or blocking.

Also probes the first-subscribe race: ``GossipClient.start()`` is not
atomic, so N subscribes racing the cold start may each open a Redis
connection while only the last assignment to ``self._redis`` is tracked —
a leaked-connection candidate.
"""

from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis

from trading_service.services.gossip_client import GossipClient


class _FakePubSub:
    def __init__(self) -> None:
        self.topic: str | None = None
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, topic: str) -> None:
        self.topic = topic

    async def unsubscribe(self, topic: str) -> None:
        self.unsubscribed.append(topic)

    async def aclose(self) -> None:
        self.closed = True

    def listen(self):
        async def _gen():
            while True:
                await asyncio.sleep(3600)
                yield  # pragma: no cover

        return _gen()


class _FakeRedis:
    """redis.asyncio.Redis stand-in; records ping/pubsub/aclose per instance."""

    instances: list[_FakeRedis] = []

    def __init__(self) -> None:
        self.pubsubs: list[_FakePubSub] = []
        self.closed = False
        self.pinged = False
        _FakeRedis.instances.append(self)

    async def ping(self) -> bool:
        self.pinged = True
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


async def _settle(predicate, timeout: float = 5.0) -> bool:
    """Yield loop turns until predicate() or timeout; return predicate()."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0)
    return predicate()


class TestConcurrentRedisSubscriptions:
    async def test_many_subscribes_then_closes_release_every_connection(self, fake_redis):
        client = GossipClient(backend="broadcast", redis_url="redis://localhost:6379")
        await client.start()
        main_redis = client._redis
        assert main_redis is not None and main_redis.pinged
        baseline = len(_FakeRedis.instances)

        n = 30
        subs = await asyncio.gather(*(client.subscribe(f"offers.load-{i % 3}") for i in range(n)))
        assert len(subs) == n

        # Listener tasks each open a dedicated connection + pubsub; wait for
        # all n to come up (they are spawned as tasks, not awaited inline).
        def listeners_ready() -> bool:
            return len([r for r in _FakeRedis.instances[baseline:] if r.pubsubs]) == n

        assert await _settle(listeners_ready)
        listener_redises = [r for r in _FakeRedis.instances[baseline:] if r.pubsubs]
        assert len(listener_redises) == n

        # Close all subscriptions concurrently, then let cancellations land.
        for sub in subs:
            sub.close()
        assert await _settle(
            lambda: all(
                r.closed and len(r.pubsubs) == 1 and r.pubsubs[0].closed and r.pubsubs[0].unsubscribed
                for r in listener_redises
            )
        )
        # Every listener pubsub saw exactly its own topic unsubscribed.
        for r in listener_redises:
            assert r.pubsubs[0].unsubscribed == [r.pubsubs[0].topic]

        await client.stop()
        assert main_redis.closed
        assert client._tasks == set()

    async def test_cold_start_race_opens_single_main_connection(self, fake_redis):
        """N subscribes racing an un-started client must not each win
        start() and leak the losers' connections (#1618, #1534-adjacent)."""
        client = GossipClient(backend="broadcast", redis_url="redis://localhost:6379")
        subs = await asyncio.gather(*(client.subscribe(f"offers.race-{i}") for i in range(20)))
        try:
            # Let listener tasks spin up so every from_url() call has happened.
            await _settle(lambda: len(client._tasks) >= 1)
            await asyncio.sleep(0)

            # Every _FakeRedis instance is accounted for iff it is either the
            # tracked main connection (client._redis) or a listener's
            # dedicated connection (has a pubsub). Anything else — e.g. a
            # second main connection created by a losing start() racer — is
            # leaked: never pinged-trackable, never closed.
            listener_ids = {id(r) for r in _FakeRedis.instances if r.pubsubs}
            tracked_id = id(client._redis) if client._redis is not None else -1
            leaked = [r for r in _FakeRedis.instances if id(r) not in listener_ids and id(r) != tracked_id]
            assert leaked == [], f"{len(leaked)} untracked Redis connection(s) leaked by start() race"
        finally:
            for sub in subs:
                sub.close()
            await client.stop()


class TestInMemoryFallbackBounds:
    async def test_concurrent_subscribe_publish_close_bounded(self):
        client = GossipClient(backend="memory-fallback", redis_url="redis://localhost:6379")
        await client.start()
        assert not client.using_redis

        n = 40
        bound = 64
        subs = await asyncio.gather(*(client.subscribe("offers.mem", max_queue_size=bound) for _ in range(n)))
        assert len(subs) == n

        # Hammer the topic: 50 publishers x 20 messages = 1000 deliveries.
        await asyncio.gather(
            *(asyncio.gather(*(client.publish_local("offers.mem", f"m{i}-{j}") for j in range(20))) for i in range(50))
        )

        for sub in subs:
            assert sub.queue.qsize() <= bound
            assert sub.queue.maxsize == bound

        for sub in subs:
            sub.close()
        # _close_mem schedules a removal task per subscription.
        assert await _settle(lambda: not client._mem_topics.get("offers.mem"))

        await client.stop()
