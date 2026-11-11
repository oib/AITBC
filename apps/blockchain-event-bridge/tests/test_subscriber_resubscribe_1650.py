"""#1650: gossip block/tx subscribers must resubscribe after a dead handle."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from blockchain_event_bridge.event_subscribers._resubscribe import (
    close_subscription,
    read_gossip_with_recovery,
    resubscribe,
)


def test_close_subscription_swallows_close_errors() -> None:
    sub = Mock()
    sub.close.side_effect = RuntimeError("already closed")
    close_subscription(sub)
    sub.close.assert_called_once()


@pytest.mark.asyncio
async def test_resubscribe_replaces_subscription() -> None:
    broker = AsyncMock()
    new_sub = object()
    broker.subscribe.return_value = new_sub
    old = Mock()

    got = await resubscribe(broker, "blocks.test", old, max_queue_size=100)

    old.close.assert_called_once()
    broker.subscribe.assert_awaited_once_with("blocks.test", max_queue_size=100)
    assert got is new_sub


@pytest.mark.asyncio
async def test_read_gossip_with_recovery_resubscribes_on_read_error() -> None:
    broker = AsyncMock()
    new_sub = AsyncMock()
    new_sub.get.return_value = {"height": 1}
    broker.subscribe.return_value = new_sub
    bad_sub = AsyncMock()
    bad_sub.get.side_effect = ConnectionError("stale handle")

    outcome = await read_gossip_with_recovery(broker, "blocks.test", bad_sub, label="Block")

    bad_sub.close.assert_called_once()
    broker.subscribe.assert_awaited_once()
    assert outcome.kind == "retry"
    assert outcome.subscription is new_sub


@pytest.mark.asyncio
async def test_read_gossip_with_recovery_returns_message() -> None:
    sub = AsyncMock()
    sub.get.return_value = {"height": 99}
    outcome = await read_gossip_with_recovery(None, "", sub, label="Block")
    assert outcome.kind == "message"
    assert outcome.message == {"height": 99}
