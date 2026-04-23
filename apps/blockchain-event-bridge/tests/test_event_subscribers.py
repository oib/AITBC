"""Tests for event subscribers."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from blockchain_event_bridge.event_subscribers.blocks import BlockEventSubscriber
from blockchain_event_bridge.event_subscribers.transactions import TransactionEventSubscriber


@pytest.mark.asyncio
async def test_block_subscriber_initialization():
    """Test block subscriber initialization."""
    from blockchain_event_bridge.config import Settings

    settings = Settings()
    subscriber = BlockEventSubscriber(settings)

    assert subscriber.settings == settings
    assert subscriber._running is False


@pytest.mark.asyncio
async def test_block_subscriber_set_bridge():
    """Test setting bridge on block subscriber."""
    from blockchain_event_bridge.config import Settings
    from blockchain_event_bridge.bridge import BlockchainEventBridge

    settings = Settings()
    subscriber = BlockEventSubscriber(settings)
    bridge = Mock(spec=BlockchainEventBridge)

    subscriber.set_bridge(bridge)
    assert subscriber._bridge == bridge


@pytest.mark.asyncio
async def test_block_subscriber_stop():
    """Test stopping block subscriber."""
    from blockchain_event_bridge.config import Settings

    settings = Settings()
    subscriber = BlockEventSubscriber(settings)

    # Start and immediately stop
    task = asyncio.create_task(subscriber.run())
    await asyncio.sleep(0.1)  # Let it start
    await subscriber.stop()

    # Cancel the task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert subscriber._running is False


@pytest.mark.asyncio
async def test_transaction_subscriber_initialization():
    """Test transaction subscriber initialization."""
    from blockchain_event_bridge.config import Settings

    settings = Settings()
    subscriber = TransactionEventSubscriber(settings)

    assert subscriber.settings == settings
    assert subscriber._running is False
