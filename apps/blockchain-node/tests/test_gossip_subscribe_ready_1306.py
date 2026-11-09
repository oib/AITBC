"""#1306: broadcast subscribe() must be able to wait until the redis SUBSCRIBE is live."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aitbc_chain.config import settings
from aitbc_chain.gossip import BroadcastGossipBackend


class _SlowPubSub:
    def __init__(self, delay: float, fail: bool = False) -> None:
        self._delay = delay
        self._fail = fail
        self.live = False

    async def subscribe(self, topic: str) -> None:
        await asyncio.sleep(self._delay)
        if self._fail:
            raise ConnectionError("boom")
        self.live = True

    async def get_message(self, **_: Any) -> None:
        await asyncio.sleep(0.05)

    async def aclose(self) -> None:
        return None


class _FakeRedis:
    pubsub_obj: _SlowPubSub

    def pubsub(self) -> _SlowPubSub:
        return _FakeRedis.pubsub_obj

    async def aclose(self) -> None:
        return None

    async def publish(self, *_: Any) -> None:
        return None


@pytest.fixture()
def backend(monkeypatch):
    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis.Redis, "from_url", staticmethod(lambda *a, **k: _FakeRedis()))
    b = BroadcastGossipBackend("redis://fake")
    return b


async def _subscribe_and_check(b, delay=0.3, fail=False):
    _FakeRedis.pubsub_obj = _SlowPubSub(delay, fail)
    await b.start()
    sub = await b.subscribe("topic.x")
    live_at_return = _FakeRedis.pubsub_obj.live
    sub.close()
    await asyncio.sleep(0.1)
    await b.shutdown()
    return live_at_return


@pytest.mark.asyncio
async def test_flag_on_waits_until_subscription_is_live(backend, monkeypatch):
    monkeypatch.setattr(settings, "gossip_subscribe_wait_ready_enabled", True)
    assert await _subscribe_and_check(backend) is True


@pytest.mark.asyncio
async def test_flag_off_returns_before_subscription_is_live(backend, monkeypatch):
    monkeypatch.setattr(settings, "gossip_subscribe_wait_ready_enabled", False)
    assert await _subscribe_and_check(backend) is False


@pytest.mark.asyncio
async def test_failed_subscribe_does_not_hang_the_caller(backend, monkeypatch):
    monkeypatch.setattr(settings, "gossip_subscribe_wait_ready_enabled", True)
    assert await asyncio.wait_for(_subscribe_and_check(backend, fail=True), timeout=3) is False


@pytest.mark.asyncio
async def test_wait_is_bounded_by_timeout(backend, monkeypatch):
    monkeypatch.setattr(settings, "gossip_subscribe_wait_ready_enabled", True)
    monkeypatch.setattr(settings, "gossip_subscribe_ready_timeout_seconds", 0.1)
    assert await asyncio.wait_for(_subscribe_and_check(backend, delay=1.0), timeout=3) is False
