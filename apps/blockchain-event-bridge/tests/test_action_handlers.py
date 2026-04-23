"""Tests for action handlers."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from blockchain_event_bridge.action_handlers.coordinator_api import CoordinatorAPIHandler
from blockchain_event_bridge.action_handlers.agent_daemon import AgentDaemonHandler
from blockchain_event_bridge.action_handlers.marketplace import MarketplaceHandler


@pytest.mark.asyncio
async def test_coordinator_api_handler_initialization():
    """Test coordinator API handler initialization."""
    handler = CoordinatorAPIHandler("http://localhost:8011", "test-key")

    assert handler.base_url == "http://localhost:8011"
    assert handler.api_key == "test-key"
    assert handler._client is None


@pytest.mark.asyncio
async def test_coordinator_api_handler_handle_block():
    """Test coordinator API handler handling a block."""
    handler = CoordinatorAPIHandler("http://localhost:8011")

    block_data = {"height": 100, "hash": "0x123"}
    transactions = [{"type": "ai_job", "hash": "0x456"}]

    with patch.object(handler, "handle_transaction", new_callable=AsyncMock) as mock_handle_tx:
        await handler.handle_block(block_data, transactions)

        mock_handle_tx.assert_called_once_with(transactions[0])


@pytest.mark.asyncio
async def test_coordinator_api_handler_close():
    """Test closing coordinator API handler."""
    handler = CoordinatorAPIHandler("http://localhost:8011")

    # Create a client first
    await handler._get_client()
    assert handler._client is not None

    await handler.close()
    assert handler._client is None


@pytest.mark.asyncio
async def test_agent_daemon_handler_initialization():
    """Test agent daemon handler initialization."""
    handler = AgentDaemonHandler("http://localhost:8006")

    assert handler.blockchain_rpc_url == "http://localhost:8006"
    assert handler._client is None


@pytest.mark.asyncio
async def test_agent_daemon_handler_handle_transaction():
    """Test agent daemon handler handling a transaction."""
    handler = AgentDaemonHandler("http://localhost:8006")

    tx_data = {
        "hash": "0x123",
        "type": "agent_message",
        "to": "agent_address",
        "payload": {"trigger": "process"}
    }

    with patch.object(handler, "_notify_agent_daemon", new_callable=AsyncMock) as mock_notify:
        await handler.handle_transaction(tx_data)

        mock_notify.assert_called_once_with(tx_data)


@pytest.mark.asyncio
async def test_agent_daemon_handler_is_agent_transaction():
    """Test checking if transaction is an agent transaction."""
    handler = AgentDaemonHandler("http://localhost:8006")

    # Agent transaction
    assert handler._is_agent_transaction({"payload": {"trigger": "test"}}) is True
    assert handler._is_agent_transaction({"payload": {"agent": "test"}}) is True

    # Not an agent transaction
    assert handler._is_agent_transaction({"payload": {"other": "test"}}) is False
    assert handler._is_agent_transaction({}) is False


@pytest.mark.asyncio
async def test_marketplace_handler_initialization():
    """Test marketplace handler initialization."""
    handler = MarketplaceHandler("http://localhost:8011", "test-key")

    assert handler.base_url == "http://localhost:8011"
    assert handler.api_key == "test-key"
    assert handler._client is None


@pytest.mark.asyncio
async def test_marketplace_handler_filter_marketplace_transactions():
    """Test filtering marketplace transactions."""
    handler = MarketplaceHandler("http://localhost:8011")

    transactions = [
        {"type": "marketplace", "hash": "0x1"},
        {"type": "transfer", "hash": "0x2"},
        {"type": "listing", "hash": "0x3"},
        {"type": "transfer", "payload": {"listing_id": "123"}, "hash": "0x4"},
    ]

    filtered = handler._filter_marketplace_transactions(transactions)

    assert len(filtered) == 3
    assert filtered[0]["hash"] == "0x1"
    assert filtered[1]["hash"] == "0x3"
    assert filtered[2]["hash"] == "0x4"
