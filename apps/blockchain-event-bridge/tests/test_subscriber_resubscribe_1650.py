"""#1650: gossip block/tx subscribers must resubscribe after a dead handle."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from blockchain_event_bridge.config import Settings
from blockchain_event_bridge.event_subscribers.blocks import BlockEventSubscriber


class _FakeSubscription:
    def __init__(self, fail_first: bool) -> None:
        self._fail_first = fail_first
        self._attempts = 0
        self.queue = asyncio.Queue()
        self.closed = False

    async def get(self) -> dict:
        self._attempts += 1
        if self._fail_first and self._attempts == 1:
            raise ConnectionError("stale subscription")
        return {"height": 42, "hash": "0xabc", "transactions": []}

    def close(self) -> None:
        self.closed = True


class _FakeBroker:
    def __init__(self) -> None:
        self.subscribe_calls = 0

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> _FakeSubscription:
        self.subscribe_calls += 1
        return _FakeSubscription(fail_first=self.subscribe_calls == 1)

    async def shutdown(self) -> None:
        return None


@pytest.mark.asyncio
async def test_block_subscriber_resubscribes_when_get_fails() -> None:
    settings = Settings(chain_id="ait-test")
    subscriber = BlockEventSubscriber(settings)
    broker = _FakeBroker()

    with (
        patch("aitbc_chain.gossip.create_backend", return_value=object()),
        patch("aitbc_chain.gossip.GossipBroker", return_value=broker),
    ):
        task = asyncio.create_task(subscriber.run())
        for _ in range(30):
            if broker.subscribe_calls >= 2:
                break
            await asyncio.sleep(0.05)
        await subscriber.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert broker.subscribe_calls >= 2
