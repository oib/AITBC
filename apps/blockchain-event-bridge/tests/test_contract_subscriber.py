"""Tests for contract event subscriber."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys

from blockchain_event_bridge.event_subscribers.contracts import ContractEventSubscriber


@pytest.mark.asyncio
async def test_contract_subscriber_initialization():
    """Test contract subscriber initialization."""
    from blockchain_event_bridge.config import Settings

    settings = Settings()
    subscriber = ContractEventSubscriber(settings)

    assert subscriber.settings == settings
    assert subscriber._running is False
    assert subscriber.contract_addresses is not None


@pytest.mark.asyncio
async def test_contract_subscriber_set_bridge():
    """Test setting bridge on contract subscriber."""
    from blockchain_event_bridge.config import Settings
    from blockchain_event_bridge.bridge import BlockchainEventBridge

    settings = Settings()
    subscriber = ContractEventSubscriber(settings)
    bridge = Mock(spec=BlockchainEventBridge)

    subscriber.set_bridge(bridge)
    assert subscriber._bridge == bridge


@pytest.mark.asyncio
async def test_contract_subscriber_disabled():
    """Test contract subscriber when disabled."""
    from blockchain_event_bridge.config import Settings

    settings = Settings(subscribe_contracts=False)
    subscriber = ContractEventSubscriber(settings)

    await subscriber.run()
    assert subscriber._running is False


@pytest.mark.asyncio
async def test_contract_subscriber_stop():
    """Test stopping contract subscriber."""
    from blockchain_event_bridge.config import Settings

    settings = Settings(subscribe_contracts=False)
    subscriber = ContractEventSubscriber(settings)

    await subscriber.stop()
    assert subscriber._running is False


@pytest.mark.asyncio
async def test_process_staking_event():
    """Test processing staking event."""
    from blockchain_event_bridge.config import Settings
    from blockchain_event_bridge.bridge import BlockchainEventBridge

    settings = Settings()
    subscriber = ContractEventSubscriber(settings)
    bridge = Mock(spec=BlockchainEventBridge)
    bridge.handle_staking_event = AsyncMock()

    subscriber.set_bridge(bridge)

    event_log = {
        "topics": ["StakeCreated"],
        "data": "{}",
        "address": "0x123"
    }

    await subscriber._handle_staking_event(event_log)
    bridge.handle_staking_event.assert_called_once_with(event_log)


@pytest.mark.asyncio
async def test_process_performance_event():
    """Test processing performance event."""
    from blockchain_event_bridge.config import Settings
    from blockchain_event_bridge.bridge import BlockchainEventBridge

    settings = Settings()
    subscriber = ContractEventSubscriber(settings)
    bridge = Mock(spec=BlockchainEventBridge)
    bridge.handle_performance_event = AsyncMock()

    subscriber.set_bridge(bridge)

    event_log = {
        "topics": ["PerformanceVerified"],
        "data": "{}",
        "address": "0x123"
    }

    await subscriber._handle_performance_event(event_log)
    bridge.handle_performance_event.assert_called_once_with(event_log)
