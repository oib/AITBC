"""Regression tests for blockchain_poa_broadcast_skipped_total semantics.

#705: the counter used to increment whenever the local lease registry was
empty, although gossip publication always proceeds via the mesh backend —
the "skipped" alerts fired on fully healthy propagation. The counter now
only increments when gossip_broker.publish actually raises.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aitbc_chain.consensus import poa
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metrics import poa_broadcast_skipped_total

CHAIN = "bc-2-skiptest"


def _proposer() -> SimpleNamespace:
    return SimpleNamespace(
        _config=SimpleNamespace(chain_id=CHAIN),
        _stop_event=asyncio.Event(),
        _logger=logging.getLogger("test"),
    )


def _block() -> SimpleNamespace:
    return SimpleNamespace(
        height=1,
        hash="0x1",
        parent_hash="0x0",
        proposer="0xabc",
        timestamp=datetime.now(UTC),
        tx_count=0,
        state_root="0x0",
        bridge_state_root="0x0",
        aux_state_root="0x0",
        signature="0xsig",
        block_metadata="{}",
    )


@pytest.mark.asyncio
async def test_zero_lease_subscribers_does_not_count_as_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publish success with zero leases must NOT increment skipped_total."""
    monkeypatch.setattr(poa.lease_tracker, "get_valid_subscribers", AsyncMock(return_value=[]))
    monkeypatch.setattr(poa.gossip_broker, "publish", AsyncMock())

    counter = poa_broadcast_skipped_total.labels(chain_id=CHAIN)
    before = counter._value.get()
    result = await PoAProposer._broadcast_block(_proposer(), _block(), [])
    assert result is True
    assert counter._value.get() == before


@pytest.mark.asyncio
async def test_publish_failure_counts_as_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real publish exception is the only genuine skip."""
    monkeypatch.setattr(poa.lease_tracker, "get_valid_subscribers", AsyncMock(return_value=["someone"]))
    monkeypatch.setattr(poa.gossip_broker, "publish", AsyncMock(side_effect=RuntimeError("bus down")))

    counter = poa_broadcast_skipped_total.labels(chain_id=CHAIN)
    before = counter._value.get()
    result = await PoAProposer._broadcast_block(_proposer(), _block(), [])
    assert result is True  # broadcast failure does not fail the proposal
    assert counter._value.get() == before + 1
