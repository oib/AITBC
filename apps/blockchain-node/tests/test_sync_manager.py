from __future__ import annotations

import asyncio
import time
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


def test_get_sync_status_unknown_chain(sync_manager):
    status = sync_manager.get_sync_status("no-such-chain")
    assert status["chain_id"] == "no-such-chain"
    assert status["mode"] == "unknown"


def test_get_sync_status_populated(sync_manager):
    state = sync_manager._chain_states["test-chain"]
    state.mode = SyncMode.SYNCED
    state.last_local_height = 42
    state.last_remote_height = 45
    state.last_push_at = time.time()
    status = sync_manager.get_sync_status("test-chain")
    assert status["chain_id"] == "test-chain"
    assert status["mode"] == "synced"
    assert status["local_height"] == 42
    assert status["remote_height"] == 45
    assert status["gap"] == 3
    assert status["last_push_seconds_ago"] is not None


def test_force_catch_up_sets_mode(sync_manager):
    _run(sync_manager.force_catch_up("test-chain"))
    assert sync_manager._chain_states["test-chain"].mode == SyncMode.CATCH_UP


def test_ensure_genesis_and_start_stop_lifecycle(monkeypatch):
    monkeypatch.setattr(settings, "supported_chains", "test-chain")
    monkeypatch.setattr(settings, "chain_id", "test-chain")
    monkeypatch.setattr(settings, "default_peer_rpc_url", "")
    monkeypatch.setattr(settings, "chain_sync_sources", "")
    monkeypatch.setattr(settings, "sync_manager_use_gossip", False)
    monkeypatch.setattr(settings, "sync_manager_use_subscription", False)
    monkeypatch.setattr(settings, "block_production_chains", "")
    sm = SyncManager(chains=["test-chain"], own_gossip=False, skip_init_db=True)

    async def _start_and_stop() -> None:
        await sm.start()
        assert "test-chain" in sm._chain_states
        assert sm._chain_states["test-chain"].chain_sync is not None
        assert len(sm._tasks) == 1
        await sm.stop()

    _run(_start_and_stop())
    assert sm._stop_event.is_set()


def test_tick_triggers_bulk_pull(sync_manager, monkeypatch):
    monkeypatch.setattr(settings, "auto_sync_threshold", 5)
    state = sync_manager._chain_states["test-chain"]
    chain_sync = MagicMock()
    chain_sync.peer_head_divergence = AsyncMock(return_value=(None, 20))
    chain_sync.get_local_height = MagicMock(return_value=1)
    chain_sync.bulk_import_from = AsyncMock(return_value=14)
    state.chain_sync = chain_sync
    state.last_local_height = 1
    state.last_remote_height = 20
    state.mode = SyncMode.SYNCED

    with (
        patch.object(sync_manager, "_should_sync_remote", return_value=True),
        patch.object(sync_manager._source_resolver, "get_sync_source", return_value="http://hub"),
    ):
        interval = _run(sync_manager._tick("test-chain"))

    assert state.mode == SyncMode.CATCH_UP
    assert state.bulk_task is not None
    assert interval == settings.sync_manager_poll_interval


def test_tick_uses_synced_poll_interval(sync_manager, monkeypatch):
    monkeypatch.setattr(settings, "sync_manager_synced_poll_interval", 30.0)
    monkeypatch.setattr(settings, "sync_manager_state_sync_interval", 0.0)
    state = sync_manager._chain_states["test-chain"]
    chain_sync = MagicMock()
    chain_sync.peer_head_divergence = AsyncMock(return_value=(None, 5))
    chain_sync.get_local_height = MagicMock(return_value=5)
    chain_sync.delta_sync_from = AsyncMock(return_value={"synced": 0})
    state.chain_sync = chain_sync
    state.last_local_height = 5
    state.last_remote_height = 5
    state.mode = SyncMode.SYNCED

    with (
        patch.object(sync_manager, "_should_sync_remote", return_value=True),
        patch.object(sync_manager._source_resolver, "get_sync_source", return_value="http://hub"),
    ):
        interval = _run(sync_manager._tick("test-chain"))

    assert state.mode == SyncMode.SYNCED
    assert interval == 30.0


def test_handle_block_skips_self_proposed(sync_manager, monkeypatch):
    monkeypatch.setattr(settings, "blockchain_mode", "hub")
    chain_sync = sync_manager._chain_states["test-chain"].chain_sync
    sync_manager._proposer_id = "local-validator"
    sync_manager._production_chains = {"test-chain"}
    result = _run(
        sync_manager.handle_block("test-chain", {"height": 5, "hash": "0xabc", "proposer": "local-validator"}, source="gossip")
    )
    assert not result.accepted
    assert "Self-proposed block" in result.reason
    assert chain_sync.import_block.call_count == 0
