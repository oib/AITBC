"""Integration tests for blockchain event bridge."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys

from blockchain_event_bridge.bridge import BlockchainEventBridge
from blockchain_event_bridge.config import Settings


@pytest.mark.asyncio
async def test_bridge_initialization():
    """Test bridge initialization."""
    settings = Settings()
    bridge = BlockchainEventBridge(settings)

    assert bridge.settings == settings
    assert bridge.is_running is False


@pytest.mark.asyncio
async def test_bridge_start_stop():
    """Test bridge start and stop."""
    settings = Settings(
        subscribe_blocks=False,
        subscribe_transactions=False,
    )
    bridge = BlockchainEventBridge(settings)

    await bridge.start()
    assert bridge.is_running is True

    await bridge.stop()
    assert bridge.is_running is False


@pytest.mark.asyncio
async def test_bridge_handle_block_event():
    """Test bridge handling a block event."""
    settings = Settings(
        enable_coordinator_api_trigger=False,
        enable_marketplace_trigger=False,
    )
    bridge = BlockchainEventBridge(settings)

    block_data = {
        "height": 100,
        "hash": "0x123",
        "transactions": []
    }

    # Should not raise an error even without handlers
    await bridge.handle_block_event(block_data)


@pytest.mark.asyncio
async def test_bridge_handle_transaction_event():
    """Test bridge handling a transaction event."""
    settings = Settings(
        enable_agent_daemon_trigger=False,
        enable_coordinator_api_trigger=False,
    )
    bridge = BlockchainEventBridge(settings)

    tx_data = {
        "hash": "0x456",
        "type": "transfer"
    }

    # Should not raise an error even without handlers
    await bridge.handle_transaction_event(tx_data)
