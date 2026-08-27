from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc_chain.config import settings
from aitbc_chain.sync_manager import ChainSyncState, SyncManager, SyncMode, block_data_callback
from aitbc_chain.sync_validator import ImportResult


@pytest.fixture
def sync_manager(monkeypatch):
    """Return a SyncManager with mocked dependencies."""
    monkeypatch.setattr(settings, "supported_chains", "test-chain")
    monkeypatch.setattr(settings, "chain_id", "test-chain")
    monkeypatch.setattr(settings, "default_peer_rpc_url", "")
    monkeypatch.setattr(settings, "chain_sync_sources", "")
    monkeypatch.setattr(settings, "sync_manager_use_gossip", False)
    monkeypatch.setattr(settings, "sync_manager_use_subscription", False)
    monkeypatch.setattr(settings, "block_production_chains", "")
    monkeypatch.setattr(settings, "sync_state_root_validation_enabled", False)

    sm = SyncManager(chains=["test-chain"], own_gossip=False, skip_init_db=True)
    sm._chain_states["test-chain"] = ChainSyncState(chain_id="test-chain")
    sm._chain_states["test-chain"].chain_sync = MagicMock()
    return sm


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_block_hash_stable(sync_manager):
    block = {"height": 1, "hash": "0xabc", "proposer": "node1"}
    assert sync_manager._block_hash(block) == "0xabc"


def test_block_hash_fallback(sync_manager):
    block = {"height": 1, "proposer": "node1"}
    h1 = sync_manager._block_hash(block)
    h2 = sync_manager._block_hash(block)
    assert h1.startswith("0x")
    assert h1 == h2


def test_handle_block_dedup(sync_manager):
    chain_sync = sync_manager._chain_states["test-chain"].chain_sync
    chain_sync.import_block.return_value = ImportResult(
        accepted=True,
        height=1,
        block_hash="0xabc",
        reason="",
    )

    block = {"height": 1, "hash": "0xabc", "proposer": "hub"}
    result = _run(sync_manager.handle_block("test-chain", block, source="gossip"))
    assert result.accepted
    assert chain_sync.import_block.call_count == 1

    # Duplicate within TTL should be rejected without second import.
    result = _run(sync_manager.handle_block("test-chain", block, source="subscription"))
    assert not result.accepted
    assert chain_sync.import_block.call_count == 1


def test_handle_block_forces_catch_up_on_gap(sync_manager):
    chain_sync = sync_manager._chain_states["test-chain"].chain_sync
    chain_sync.import_block.return_value = ImportResult(
        accepted=False,
        height=10,
        block_hash="0xdef",
        reason="Gap detected: our height: 1, received: 10",
    )
    chain_sync.bulk_import_from = AsyncMock(return_value=8)

    block = {"height": 10, "hash": "0xdef", "proposer": "hub"}
    with (
        patch.object(sync_manager, "_should_sync_remote", return_value=True),
        patch.object(sync_manager._source_resolver, "get_sync_source", return_value="http://hub"),
    ):
        result = _run(sync_manager.handle_block("test-chain", block, source="gossip"))

    assert not result.accepted
    assert sync_manager._chain_states["test-chain"].mode == SyncMode.CATCH_UP
    assert sync_manager._chain_states["test-chain"].bulk_task is not None


def test_block_data_callback_format(sync_manager):
    with patch.object(SyncManager, "handle_block", new_callable=AsyncMock) as mock_handle:
        cb = block_data_callback(sync_manager, "test-chain")
        _run(cb({"height": 5, "hash": "0x123"}))
        mock_handle.assert_awaited_once_with("test-chain", {"height": 5, "hash": "0x123"}, source="subscription")
