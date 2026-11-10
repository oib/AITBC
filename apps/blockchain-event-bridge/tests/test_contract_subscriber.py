"""Tests for contract event subscriber."""

from unittest.mock import AsyncMock, Mock

import pytest
from blockchain_event_bridge.event_subscribers.contracts import ContractEventSubscriber


def _pollable_subscriber() -> ContractEventSubscriber:
    """Subscriber with one configured contract and a checkpoint to advance from."""
    from blockchain_event_bridge.config import Settings

    settings = Settings(agent_staking_address="0xabc")
    subscriber = ContractEventSubscriber(settings)
    subscriber.last_processed_blocks["AgentStaking"] = 50
    client = AsyncMock()
    client.get = AsyncMock(return_value={"height": 100})  # to_block = 88 > 50
    subscriber._client = client
    return subscriber


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
    from blockchain_event_bridge.bridge import BlockchainEventBridge
    from blockchain_event_bridge.config import Settings

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
    from blockchain_event_bridge.bridge import BlockchainEventBridge
    from blockchain_event_bridge.config import Settings

    settings = Settings()
    subscriber = ContractEventSubscriber(settings)
    bridge = Mock(spec=BlockchainEventBridge)
    bridge.handle_staking_event = AsyncMock()

    subscriber.set_bridge(bridge)

    event_log = {"topics": ["StakeCreated"], "data": "{}", "address": "0x123"}

    await subscriber._handle_staking_event(event_log)
    bridge.handle_staking_event.assert_called_once_with(event_log)


@pytest.mark.asyncio
async def test_process_performance_event():
    """Test processing performance event."""
    from blockchain_event_bridge.bridge import BlockchainEventBridge
    from blockchain_event_bridge.config import Settings

    settings = Settings()
    subscriber = ContractEventSubscriber(settings)
    bridge = Mock(spec=BlockchainEventBridge)
    bridge.handle_performance_event = AsyncMock()

    subscriber.set_bridge(bridge)

    event_log = {"topics": ["PerformanceVerified"], "data": "{}", "address": "0x123"}

    await subscriber._handle_performance_event(event_log)
    bridge.handle_performance_event.assert_called_once_with(event_log)


@pytest.mark.asyncio
async def test_poll_advances_checkpoint_on_valid_empty_logs():
    """A well-formed empty scan still advances the checkpoint (control case)."""
    subscriber = _pollable_subscriber()
    subscriber._client.post = AsyncMock(return_value={"logs": [], "count": 0})

    await subscriber._poll_contract_events()

    assert subscriber.last_processed_blocks["AgentStaking"] == 88


@pytest.mark.asyncio
async def test_poll_error_body_does_not_advance_checkpoint():
    """BRIDGE-EVT-LOGS-1 (#1430): HTTP-200 {"error": ...} must not skip the range."""
    subscriber = _pollable_subscriber()
    subscriber._client.post = AsyncMock(return_value={"error": {"code": -32000, "message": "boom"}})

    await subscriber._poll_contract_events()

    assert subscriber.last_processed_blocks["AgentStaking"] == 50
    subscriber._client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_missing_logs_key_does_not_advance_checkpoint():
    """A 200 body without a 'logs' list is a poll failure, not an empty scan."""
    subscriber = _pollable_subscriber()
    subscriber._client.post = AsyncMock(return_value={"count": 0, "result": None})

    await subscriber._poll_contract_events()

    assert subscriber.last_processed_blocks["AgentStaking"] == 50


@pytest.mark.asyncio
async def test_poll_non_list_logs_does_not_advance_checkpoint():
    """'logs' present but not a list is also a malformed response."""
    subscriber = _pollable_subscriber()
    subscriber._client.post = AsyncMock(return_value={"logs": "unexpected"})

    await subscriber._poll_contract_events()

    assert subscriber.last_processed_blocks["AgentStaking"] == 50


@pytest.mark.asyncio
async def test_poll_malformed_json_raises_before_checkpoint():
    """A body that fails JSON decoding raises out of client.post — checkpoint held."""
    subscriber = _pollable_subscriber()
    subscriber._client.post = AsyncMock(side_effect=ValueError("Expecting value: line 1 column 1"))

    await subscriber._poll_contract_events()

    assert subscriber.last_processed_blocks["AgentStaking"] == 50
