"""Concurrency pins for the #1537 SimpleBroadcast subscriber bound.

Pre-fix every subscriber got an unbounded ``asyncio.Queue`` and publish used
``await queue.put`` — one stalled WebSocket client grew memory without limit
and head-of-line blocked the publisher behind it. Now queues are capped at
``_MAX_QUEUE_SIZE`` and publish drops on full via ``put_nowait``.

These tests hammer publish from many concurrent tasks against stalled and
draining subscribers and assert the cap holds, drops never raise, and
unsubscribes stay clean.
"""

from __future__ import annotations

import asyncio


from aitbc_chain.gossip.relay import SimpleBroadcast

_CHANNEL = "blocks.concurrency"
_MESSAGES = 1000
_PUBLISHERS = 50


async def test_full_subscriber_queue_capped_under_concurrent_publish():
    broadcast = SimpleBroadcast()
    stalled = await broadcast.subscribe(_CHANNEL)
    draining = await broadcast.subscribe(_CHANNEL)

    received: list[str] = []

    async def drain() -> None:
        async for message in draining:
            received.append(message)
            if len(received) >= _MESSAGES:
                return

    drain_task = asyncio.create_task(drain())
    try:
        # 50 publishers x 20 messages each = _MESSAGES total, all gathered.
        await asyncio.gather(
            *(asyncio.gather(*(broadcast.publish(_CHANNEL, f"m{i}-{j}") for j in range(20))) for i in range(_PUBLISHERS))
        )
    finally:
        # Stop the drain loop: it exits on its own after _MESSAGES items, but
        # drops mean it may never reach that — cancel defensively.
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass

    # The stalled subscriber's queue is exactly at the cap — never above,
    # and publish never raised or blocked on it.
    assert stalled.queue.qsize() == SimpleBroadcast._MAX_QUEUE_SIZE
    assert stalled.queue.maxsize == SimpleBroadcast._MAX_QUEUE_SIZE
    # The draining subscriber may legitimately miss dropped messages, but it
    # must have received a substantial prefix — drops only start once its
    # queue fills.
    assert len(received) > 0


async def test_publish_to_unsubscribed_channel_is_noop():
    broadcast = SimpleBroadcast()
    # No subscribers at all: gather of publishes must not raise.
    await asyncio.gather(*(broadcast.publish("no.such.channel", "x") for _ in range(50)))


async def test_concurrent_subscribe_unsubscribe_leaves_no_strays():
    broadcast = SimpleBroadcast()

    async def cycle(i: int) -> None:
        async with await broadcast.subscribe(_CHANNEL) as sub:
            await broadcast.publish(_CHANNEL, f"hello-{i}")
            await sub.queue.get()

    await asyncio.gather(*(cycle(i) for i in range(30)))
    assert broadcast._subscribers.get(_CHANNEL, []) == []


async def test_late_subscriber_gets_new_messages_after_flood():
    broadcast = SimpleBroadcast()
    stalled = await broadcast.subscribe(_CHANNEL)
    await asyncio.gather(*(broadcast.publish(_CHANNEL, f"flood-{i}") for i in range(600)))
    assert stalled.queue.qsize() == SimpleBroadcast._MAX_QUEUE_SIZE

    late = await broadcast.subscribe(_CHANNEL)
    await broadcast.publish(_CHANNEL, "after-flood")
    assert await asyncio.wait_for(late.queue.get(), timeout=1) == "after-flood"
