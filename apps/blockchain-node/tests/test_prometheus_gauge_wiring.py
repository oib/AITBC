"""Regression: the prometheus_client gauges behind alert rules must emit.

SyncLagHigh (blockchain_sync_lag_blocks > 10) and MempoolFull
(blockchain_mempool_pending_count > 9000) were dead on every host: the
Gauge objects were declared in metrics.py but nothing ever set them — the
runtime only wrote the legacy metrics_registry names. Absence looked like
zero, so the rules could never fire. These tests fail if the wiring is
dropped again.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from prometheus_client import REGISTRY

from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool
from aitbc_chain.sync_manager import ChainSyncState, SyncManager


def _run(coro):
    return asyncio.run(coro)


def _metric_value(name: str, chain_id: str) -> float | None:
    """Current sample value for a labelled series, or None if the series does not exist."""
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and sample.labels.get("chain_id") == chain_id:
                return sample.value
    return None


class TestMempoolPendingGauge:
    def test_inmemory_add_and_drain_update_gauge(self):
        chain = "gauge-wiring-memory"
        pool = InMemoryMempool(chain_id=chain)
        assert _metric_value("blockchain_mempool_pending_count", chain) is None

        tx = {"from": "0xabc", "to": "0xdef", "amount": 1, "fee": 0, "nonce": 1, "signature": "s"}
        pool.add(dict(tx), chain_id=chain, tx_hash="0xgaugew1")

        assert _metric_value("blockchain_mempool_pending_count", chain) == 1.0
        assert _metric_value("blockchain_mempool_pending_size_bytes", chain) > 0.0

        pool.drain(10, 10**9, chain_id=chain)
        assert _metric_value("blockchain_mempool_pending_count", chain) == 0.0
        assert _metric_value("blockchain_mempool_pending_size_bytes", chain) == 0.0

    def test_inmemory_remove_updates_gauge(self):
        chain = "gauge-wiring-remove"
        pool = InMemoryMempool(chain_id=chain)
        pool.add({"fee": 1}, chain_id=chain, tx_hash="0xgaugew2")
        pool.remove("0xgaugew2", chain_id=chain)
        assert _metric_value("blockchain_mempool_pending_count", chain) == 0.0

    def test_database_mempool_updates_gauge(self, tmp_path):
        chain = "gauge-wiring-db"
        pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}")
        tx = {"from": "0xabc", "to": "0xdef", "amount": 1, "fee": 0, "nonce": 1, "signature": "s"}
        pool.add(dict(tx), chain_id=chain)

        assert _metric_value("blockchain_mempool_pending_count", chain) == 1.0
        assert _metric_value("blockchain_mempool_pending_size_bytes", chain) > 0.0

        pool.drain(10, 10**9, chain_id=chain)
        assert _metric_value("blockchain_mempool_pending_count", chain) == 0.0


class TestSyncLagGauge:
    def test_tick_sets_sync_lag(self, monkeypatch):
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "auto_sync_threshold", 10)
        chain = "gauge-wiring-sync"
        sm = SyncManager(chains=[chain], own_gossip=False, skip_init_db=True)
        state = ChainSyncState(chain_id=chain)
        chain_sync = MagicMock()
        chain_sync.peer_head_divergence = AsyncMock(return_value=(None, 12))
        chain_sync.get_local_height = MagicMock(return_value=5)
        state.chain_sync = chain_sync
        sm._chain_states[chain] = state

        with (
            patch.object(sm, "_should_sync_remote", return_value=True),
            patch.object(sm._source_resolver, "get_sync_source", return_value="http://hub"),
        ):
            _run(sm._tick(chain))

        assert _metric_value("blockchain_sync_lag_blocks", chain) == 7.0

    def test_tick_reports_zero_when_caught_up(self, monkeypatch):
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "sync_manager_synced_poll_interval", 30.0)
        monkeypatch.setattr(settings, "sync_manager_state_sync_interval", 0.0)
        chain = "gauge-wiring-synced"
        sm = SyncManager(chains=[chain], own_gossip=False, skip_init_db=True)
        state = ChainSyncState(chain_id=chain)
        chain_sync = MagicMock()
        chain_sync.peer_head_divergence = AsyncMock(return_value=(None, 5))
        chain_sync.get_local_height = MagicMock(return_value=5)
        chain_sync.delta_sync_from = AsyncMock(return_value={"synced": 0})
        state.chain_sync = chain_sync
        sm._chain_states[chain] = state

        with (
            patch.object(sm, "_should_sync_remote", return_value=True),
            patch.object(sm._source_resolver, "get_sync_source", return_value="http://hub"),
        ):
            _run(sm._tick(chain))

        assert _metric_value("blockchain_sync_lag_blocks", chain) == 0.0
