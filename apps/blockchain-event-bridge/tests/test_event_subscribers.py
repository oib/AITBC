"""Tests for event subscribers."""

import asyncio
from unittest.mock import Mock

import pytest
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
    from blockchain_event_bridge.bridge import BlockchainEventBridge
    from blockchain_event_bridge.config import Settings

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


@pytest.mark.asyncio
async def test_bridge_stop_calls_subscriber_stops():
    """BRIDGE-EVT-SUBSCRIBER-1 (#1431): stop() must run each subscriber's stop()."""
    from unittest.mock import AsyncMock

    from blockchain_event_bridge.bridge import BlockchainEventBridge
    from blockchain_event_bridge.config import Settings

    bridge = BlockchainEventBridge(Settings())
    bridge._running = True
    bridge.block_subscriber = Mock()
    bridge.block_subscriber.stop = AsyncMock()
    bridge.transaction_subscriber = Mock()
    bridge.transaction_subscriber.stop = AsyncMock()
    # ContractEventSubscriber.stop is synchronous — returns None.
    bridge.contract_subscriber = Mock()
    bridge.contract_subscriber.stop = Mock(return_value=None)

    await bridge.stop()

    bridge.block_subscriber.stop.assert_awaited_once()
    bridge.transaction_subscriber.stop.assert_awaited_once()
    bridge.contract_subscriber.stop.assert_called_once()
    assert bridge.is_running is False


@pytest.mark.asyncio
async def test_bridge_stop_contains_subscriber_stop_errors():
    """One failing subscriber stop must not skip the others."""
    from unittest.mock import AsyncMock

    from blockchain_event_bridge.bridge import BlockchainEventBridge
    from blockchain_event_bridge.config import Settings

    bridge = BlockchainEventBridge(Settings())
    bridge._running = True
    bridge.block_subscriber = Mock()
    bridge.block_subscriber.stop = AsyncMock(side_effect=RuntimeError("broker gone"))
    bridge.transaction_subscriber = Mock()
    bridge.transaction_subscriber.stop = AsyncMock()
    bridge.contract_subscriber = Mock()
    bridge.contract_subscriber.stop = Mock(return_value=None)

    await bridge.stop()

    bridge.transaction_subscriber.stop.assert_awaited_once()
    bridge.contract_subscriber.stop.assert_called_once()
    assert bridge.is_running is False
