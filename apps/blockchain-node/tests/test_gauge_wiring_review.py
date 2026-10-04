"""Task 85 adversarial-review probes for 09eadc5999.

Two defect probes are strict-xfail until fixed:

- a failed remote-head fetch reports sync_lag_blocks == 0 (fabricated
  "synced") because peer_head_divergence returns (None, -1) and
  gap = max(0, -1 - local) collapses to 0.
- the submit_market_transaction GPU_REGISTER branch skips
  _validate_transaction_admission, so a request-supplied chain_id reaches
  mempool.add and mints an unbounded blockchain_mempool_pending_count
  label series.

Plus one concurrency consistency check (expected to pass): the gauge must
equal the real pool size at rest after concurrent add/remove/drain/evict.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool
from aitbc_chain.sync_manager import ChainSyncState, SyncManager


def _run(coro):
    return asyncio.run(coro)


def _metric_value(name: str, chain_id: str) -> float | None:
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and sample.labels.get("chain_id") == chain_id:
                return sample.value
    return None


class TestGaugeConsistencyUnderConcurrency:
    """Threads adding, removing, draining and evicting on both backends.

    The gauge must equal the real pool size once the workers join -- a
    missed or double-counted refresh would leave a permanent discrepancy.
    """

    def _hammer(self, pool, chain: str) -> None:
        stop = threading.Event()
        errors: list[BaseException] = []

        def adder(sender: str, prefix: int, nonce_offset: int) -> None:
            try:
                for i in range(200):
                    pool.add(
                        {"from": sender, "to": "0xb", "fee": i, "nonce": nonce_offset + i, "signature": "s"},
                        chain_id=chain,
                        tx_hash=f"0x{prefix:02x}{i:06x}",
                    )
            except BaseException as e:  # noqa: BLE001 -- record, assert later
                errors.append(e)

        def remover() -> None:
            try:
                while not stop.is_set():
                    for i in range(200):
                        pool.remove(f"0x00{i:06x}", chain_id=chain)
            except BaseException as e:
                errors.append(e)

        def drainer() -> None:
            try:
                while not stop.is_set():
                    pool.drain(5, 10**9, chain_id=chain)
            except BaseException as e:
                errors.append(e)

        def evictor() -> None:
            try:
                while not stop.is_set():
                    pool.evict_expired(0.001)
            except BaseException as e:
                errors.append(e)

        # Distinct senders and disjoint nonce ranges keep the adds free of the
        # mempool's per-(sender, nonce) slot rule -- a collision there is
        # mempool policy noise, not a gauge-consistency signal.
        workers = [
            threading.Thread(target=adder, args=("0xaaaa", 0x00, 0)),
            threading.Thread(target=adder, args=("0xbbbb", 0x10, 1000)),
            threading.Thread(target=remover),
            threading.Thread(target=drainer),
            threading.Thread(target=evictor),
        ]
        for w in workers[:2]:
            w.start()
        for w in workers[2:]:
            w.start()
        for w in workers[:2]:
            w.join(timeout=60)
        stop.set()
        for w in workers[2:]:
            w.join(timeout=60)
        assert not errors, f"worker errors: {errors!r}"

    def test_inmemory_gauge_matches_pool_at_rest(self, tmp_path):
        chain = "gauge-conc-mem"
        pool = InMemoryMempool(chain_id=chain)
        self._hammer(pool, chain)
        time.sleep(0.05)
        real = pool.size(chain_id=chain)
        gauge = _metric_value("blockchain_mempool_pending_count", chain)
        assert gauge == float(real), f"gauge {gauge} != pool {real}"

    def test_database_gauge_matches_pool_at_rest(self, tmp_path):
        chain = "gauge-conc-db"
        pool = DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}")
        self._hammer(pool, chain)
        time.sleep(0.05)
        real = pool.size(chain_id=chain)
        gauge = _metric_value("blockchain_mempool_pending_count", chain)
        assert gauge == float(real), f"gauge {gauge} != pool {real}"


class TestSyncLagOnRemoteFailure:
    """When the remote head cannot be read the lag gauge must not read 0.

    peer_head_divergence swallows fetch errors into (None, -1); today the
    tick then computes gap = max(0, -1 - local) = 0 and publishes a
    fabricated 'perfectly synced' while the node is blind. Desired: skip
    the update (keep the last known value or stay absent).
    """

    def _tick_with_remote(self, monkeypatch, chain: str, remote: int, local: int = 5):
        sm = SyncManager(chains=[chain], own_gossip=False, skip_init_db=True)
        state = ChainSyncState(chain_id=chain)
        chain_sync = MagicMock()
        chain_sync.peer_head_divergence = AsyncMock(return_value=(None, remote))
        chain_sync.get_local_height = MagicMock(return_value=local)
        chain_sync.delta_sync_from = AsyncMock(return_value={"synced": 0})
        state.chain_sync = chain_sync
        sm._chain_states[chain] = state
        with (
            patch.object(sm, "_should_sync_remote", return_value=True),
            patch.object(sm._source_resolver, "get_sync_source", return_value="http://hub"),
        ):
            try:
                _run(sm._tick(chain))
            except Exception:
                pass  # the gauge write happens before any downstream failure

    @pytest.mark.xfail(
        strict=True,
        reason="remote_height=-1 collapses to gap 0: a dead peer fabricates 'synced' on blockchain_sync_lag_blocks",
    )
    def test_failed_remote_fetch_must_not_report_zero(self, monkeypatch):
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "auto_sync_threshold", 10)
        chain = "gauge-remote-dead"
        # A healthy tick first: lag 7 lands on the gauge.
        self._tick_with_remote(monkeypatch, chain, remote=12)
        assert _metric_value("blockchain_sync_lag_blocks", chain) == 7.0
        # Now the peer dies (divergence helper returns -1). The gauge must
        # keep 7 or go absent -- never fabricate 0.
        self._tick_with_remote(monkeypatch, chain, remote=-1)
        assert _metric_value("blockchain_sync_lag_blocks", chain) != 0.0


class TestMempoolChainLabelCardinality:
    """An unsupported chain_id must never reach the mempool or the gauge.

    submit_market_transaction's GPU_REGISTER branch skips
    _validate_transaction_admission -- the only supported-chain whitelist on
    the public intake -- so a signed request with chain_id='bogus' mints a
    new blockchain_mempool_pending_count{chain_id=...} series. Rate-limited
    (50/min) but unbounded over time: a Prometheus cardinality bomb.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="GPU_REGISTER branch skips the supported-chain check; request chain_id reaches mempool.add and the label",
    )
    def test_gpu_register_with_unsupported_chain_mints_no_label(self, monkeypatch, tmp_path):
        from aitbc_chain.rpc import transactions as tx_routes
        from aitbc_chain import mempool as mempool_mod

        chain = "bogus-chain-t85"
        pool = InMemoryMempool(chain_id=chain)
        monkeypatch.setattr(mempool_mod, "get_mempool", lambda: pool)
        monkeypatch.setattr(tx_routes, "verify_transaction_signature", lambda *a, **k: True)
        monkeypatch.setattr(tx_routes, "_refuse_retired_gpu", lambda *a, **k: None)
        monkeypatch.setattr(tx_routes, "_queue_peer_fanout", lambda *a, **k: None)

        request = SimpleNamespace(
            client=SimpleNamespace(host="probe"),
            url=SimpleNamespace(path="/rpc/transactions/market"),
            headers={},
            state=SimpleNamespace(),
        )
        tx = {
            "type": "GPU_REGISTER",
            "chain_id": chain,
            "from": "0xattacker000000000000000000000000000000",
            "to": "0xattacker000000000000000000000000000000",
            "amount": 0,
            "fee": 0,
            "nonce": 0,
            "signature": "0xsigned-by-attacker",
            "payload": {"action": "register", "gpu_id": "g1"},
        }
        try:
            # __wrapped__ bypasses the rate_limit decorator so the probe
            # exercises the route body directly regardless of env.
            _run(tx_routes.submit_market_transaction.__wrapped__(request, tx))
        except Exception:
            pass  # the invariant is the pool/label, not the return path

        assert pool.size(chain_id=chain) == 0
        assert _metric_value("blockchain_mempool_pending_count", chain) is None
