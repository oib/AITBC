"""Defect-sweep pins for the contract subscriber and bridge lifecycle.

#1429 — a contract with no checkpoint entry used to default its scan cursor
to ``to_block`` itself, skipping that contract's events forever after a
failed ``_initialize_block_tracking``.

#1430 — an ``/eth_getLogs`` 200 body without a ``logs`` list (JSON-RPC-style
error) advanced the checkpoint as if the range were empty.

#1431 — ``BlockchainEventBridge.stop()`` cancelled the subscriber tasks but
never called the subscribers' ``stop()``, leaking the broker connection and
leaving ``_running`` set so a restart could not resubscribe.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from blockchain_event_bridge.bridge import BlockchainEventBridge
from blockchain_event_bridge.config import Settings
from blockchain_event_bridge.event_subscribers.contracts import ContractEventSubscriber


def _subscriber(**overrides) -> ContractEventSubscriber:
    settings = Settings(subscribe_contracts=True, market_address="0x" + "ab" * 20, **overrides)
    return ContractEventSubscriber(settings)


class _FakeClient:
    """Minimal stand-in for AsyncAITBCHTUPClient used by the poll loop."""

    def __init__(self, head: int, logs_response):
        self._head = head
        self._logs_response = logs_response
        self.posts: list[dict] = []

    async def get(self, endpoint, **kwargs):
        assert endpoint == "/head"
        return {"height": self._head}

    async def post(self, endpoint, json=None, **kwargs):
        assert endpoint == "/eth_getLogs"
        self.posts.append(json)
        return self._logs_response


@pytest.mark.asyncio
async def test_missing_checkpoint_seeds_bounded_lookback_instead_of_skipping():
    """#1429: no last_processed_blocks entry must not mean 'already at head'."""
    sub = _subscriber()
    sub._client = _FakeClient(head=200, logs_response={"logs": []})
    assert sub.last_processed_blocks == {}

    await sub._poll_contract_events()

    # current_height - 100 = 100 seeded, then scanned 101..188 (head-12).
    assert sub.last_processed_blocks["AgentServiceMarket"] == 188
    assert len(sub._client.posts) == 1
    assert sub._client.posts[0]["from_block"] == 101
    assert sub._client.posts[0]["to_block"] == 188


@pytest.mark.asyncio
async def test_error_shaped_logs_response_does_not_advance_checkpoint():
    """#1430: {"error": ...} or a missing logs key is a failed scan."""
    sub = _subscriber()
    sub.last_processed_blocks["AgentServiceMarket"] = 100
    sub._client = _FakeClient(head=200, logs_response={"error": {"code": -32602, "message": "bad range"}})

    await sub._poll_contract_events()

    # Checkpoint must stay at 100 so the range is retried next poll.
    assert sub.last_processed_blocks["AgentServiceMarket"] == 100


@pytest.mark.asyncio
async def test_logs_response_without_logs_key_does_not_advance_checkpoint():
    sub = _subscriber()
    sub.last_processed_blocks["AgentServiceMarket"] = 100
    sub._client = _FakeClient(head=200, logs_response={"unexpected": "shape"})

    await sub._poll_contract_events()

    assert sub.last_processed_blocks["AgentServiceMarket"] == 100


@pytest.mark.asyncio
async def test_valid_empty_logs_still_advances_checkpoint():
    """Guard against over-correction: a genuine empty result commits."""
    sub = _subscriber()
    sub.last_processed_blocks["AgentServiceMarket"] = 100
    sub._client = _FakeClient(head=200, logs_response={"logs": []})

    await sub._poll_contract_events()

    assert sub.last_processed_blocks["AgentServiceMarket"] == 188


@pytest.mark.asyncio
async def test_bridge_stop_calls_each_subscriber_stop():
    """#1431: stop() must run subscriber teardown, not just cancel tasks."""
    bridge = BlockchainEventBridge(Settings())
    bridge._running = True

    block_sub = Mock()
    block_sub.stop = AsyncMock()
    tx_sub = Mock()
    tx_sub.stop = AsyncMock()
    contract_sub = Mock()
    contract_sub.stop = AsyncMock()
    bridge.block_subscriber = block_sub
    bridge.transaction_subscriber = tx_sub
    bridge.contract_subscriber = contract_sub

    await bridge.stop()

    block_sub.stop.assert_awaited_once()
    tx_sub.stop.assert_awaited_once()
    contract_sub.stop.assert_awaited_once()
    assert bridge.is_running is False


@pytest.mark.asyncio
async def test_bridge_stop_survives_a_failing_subscriber():
    """One bad subscriber must not block the others' teardown."""
    bridge = BlockchainEventBridge(Settings())
    bridge._running = True

    bad = Mock()
    bad.stop = Mock(side_effect=RuntimeError("boom"))
    good = Mock()
    good.stop = AsyncMock()
    bridge.block_subscriber = bad
    bridge.transaction_subscriber = good
    bridge.contract_subscriber = None

    await bridge.stop()

    good.stop.assert_awaited_once()
    assert bridge.is_running is False
