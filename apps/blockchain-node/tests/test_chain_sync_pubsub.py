"""#1535 pin: chain_sync must poll pubsub with a timeout, not listen().

Pre-fix, ``_receive_blocks`` used ``pubsub.listen()`` — a blocking socket
read that only checks ``_stop_event`` after a message arrives, so
``stop()`` could not interrupt it and a silently-dead Redis connection hung
the receiver task (and service shutdown) forever. The fix polls
``get_message(timeout=0.5)`` like gossip/backends/broadcast.py.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aitbc_chain.chain_sync import ChainSyncService


class _FakePubSub:
    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self.messages = list(messages or [])
        self.subscribed: list[str] = []
        self.closed = False
        self.get_message_calls = 0

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float | None = None):
        self.get_message_calls += 1
        # Real get_message awaits socket I/O for up to ``timeout``; yield so
        # the receiver loop doesn't starve the event loop in tests.
        await asyncio.sleep(0)
        if self.messages:
            return self.messages.pop(0)
        return None  # timeout elapsed with nothing pending

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


def _service(pubsub: _FakePubSub) -> ChainSyncService:
    svc = ChainSyncService(redis_url="redis://unused", node_id="node-x", chain_id="test-chain")
    svc._redis = _FakeRedis(pubsub)
    svc._import_block = AsyncMock()  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
async def test_stop_is_responsive_when_no_messages_arrive():
    """listen() would park forever here; get_message(timeout) must not."""
    pubsub = _FakePubSub(messages=[])  # connection alive but silent
    svc = _service(pubsub)

    task = asyncio.create_task(svc._receive_blocks())
    await asyncio.wait_for(svc._receiver_ready.wait(), timeout=2)
    assert pubsub.subscribed == ["blocks.test-chain"]

    svc._stop_event.set()
    await asyncio.wait_for(task, timeout=5)  # would hang pre-fix
    assert pubsub.closed
    assert pubsub.get_message_calls >= 1


@pytest.mark.asyncio
async def test_block_messages_are_processed():
    from aitbc_chain.network.compression import encode_payload

    block = {"height": 7, "proposer": "other-node", "chain_id": "test-chain"}
    pubsub = _FakePubSub(messages=[{"type": "message", "data": encode_payload(block)}, {"type": "pmessage"}])
    svc = _service(pubsub)

    task = asyncio.create_task(svc._receive_blocks())
    await asyncio.wait_for(svc._receiver_ready.wait(), timeout=2)

    # Let the loop drain the queued messages, then stop.
    for _ in range(100):
        if svc._import_block.await_count >= 1:
            break
        await asyncio.sleep(0.01)
    svc._stop_event.set()
    await asyncio.wait_for(task, timeout=5)

    svc._import_block.assert_awaited_once_with(block)  # type: ignore[attr-defined]
    assert pubsub.closed
