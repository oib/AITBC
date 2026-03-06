"""Tests for mempool implementations (InMemory and Database-backed)"""

import json
import os
import tempfile
import time
import pytest

from aitbc_chain.mempool import (
    InMemoryMempool,
    DatabaseMempool,
    PendingTransaction,
    compute_tx_hash,
    _estimate_size,
    init_mempool,
    get_mempool,
)
from aitbc_chain.metrics import metrics_registry


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


class TestComputeTxHash:
    def test_deterministic(self):
        tx = {"sender": "alice", "recipient": "bob", "fee": 10}
        assert compute_tx_hash(tx) == compute_tx_hash(tx)

    def test_different_for_different_tx(self):
        tx1 = {"sender": "alice", "fee": 1}
        tx2 = {"sender": "bob", "fee": 1}
        assert compute_tx_hash(tx1) != compute_tx_hash(tx2)

    def test_hex_prefix(self):
        tx = {"sender": "alice"}
        assert compute_tx_hash(tx).startswith("0x")


class TestInMemoryMempool:
    def test_add_and_list(self):
        pool = InMemoryMempool()
        tx = {"sender": "alice", "recipient": "bob", "fee": 5}
        tx_hash = pool.add(tx)
        assert tx_hash.startswith("0x")
        txs = pool.list_transactions()
        assert len(txs) == 1
        assert txs[0].tx_hash == tx_hash
        assert txs[0].fee == 5

    def test_duplicate_ignored(self):
        pool = InMemoryMempool()
        tx = {"sender": "alice", "fee": 1}
        h1 = pool.add(tx)
        h2 = pool.add(tx)
        assert h1 == h2
        assert pool.size() == 1

    def test_min_fee_rejected(self):
        pool = InMemoryMempool(min_fee=10)
        with pytest.raises(ValueError, match="below minimum"):
            pool.add({"sender": "alice", "fee": 5})

    def test_min_fee_accepted(self):
        pool = InMemoryMempool(min_fee=10)
        pool.add({"sender": "alice", "fee": 10})
        assert pool.size() == 1

    def test_max_size_eviction(self):
        pool = InMemoryMempool(max_size=2)
        pool.add({"sender": "a", "fee": 1, "nonce": 1})
        pool.add({"sender": "b", "fee": 5, "nonce": 2})
        # Adding a 3rd should evict the lowest fee
        pool.add({"sender": "c", "fee": 10, "nonce": 3})
        assert pool.size() == 2
        txs = pool.list_transactions()
        fees = sorted([t.fee for t in txs])
        assert fees == [5, 10]  # fee=1 was evicted

    def test_drain_by_fee_priority(self):
        pool = InMemoryMempool()
        pool.add({"sender": "low", "fee": 1, "nonce": 1})
        pool.add({"sender": "high", "fee": 100, "nonce": 2})
        pool.add({"sender": "mid", "fee": 50, "nonce": 3})

        drained = pool.drain(max_count=2, max_bytes=1_000_000)
        assert len(drained) == 2
        assert drained[0].fee == 100  # highest first
        assert drained[1].fee == 50
        assert pool.size() == 1  # low fee remains

    def test_drain_respects_max_count(self):
        pool = InMemoryMempool()
        for i in range(10):
            pool.add({"sender": f"s{i}", "fee": i, "nonce": i})
        drained = pool.drain(max_count=3, max_bytes=1_000_000)
        assert len(drained) == 3
        assert pool.size() == 7

    def test_drain_respects_max_bytes(self):
        pool = InMemoryMempool()
        # Each tx is ~33 bytes serialized
        for i in range(5):
            pool.add({"sender": f"s{i}", "fee": i, "nonce": i})
        # Drain with byte limit that fits only one tx (~33 bytes each)
        drained = pool.drain(max_count=100, max_bytes=34)
        assert len(drained) == 1  # only one fits
        assert pool.size() == 4

    def test_remove(self):
        pool = InMemoryMempool()
        tx_hash = pool.add({"sender": "alice", "fee": 1})
        assert pool.size() == 1
        assert pool.remove(tx_hash) is True
        assert pool.size() == 0
        assert pool.remove(tx_hash) is False

    def test_size(self):
        pool = InMemoryMempool()
        assert pool.size() == 0
        pool.add({"sender": "a", "fee": 1, "nonce": 1})
        pool.add({"sender": "b", "fee": 2, "nonce": 2})
        assert pool.size() == 2


class TestDatabaseMempool:
    @pytest.fixture
    def db_pool(self, tmp_path):
        db_path = str(tmp_path / "mempool.db")
        return DatabaseMempool(db_path, max_size=100, min_fee=0)

    def test_add_and_list(self, db_pool):
        tx = {"sender": "alice", "recipient": "bob", "fee": 5}
        tx_hash = db_pool.add(tx)
        assert tx_hash.startswith("0x")
        txs = db_pool.list_transactions()
        assert len(txs) == 1
        assert txs[0].tx_hash == tx_hash
        assert txs[0].fee == 5

    def test_duplicate_ignored(self, db_pool):
        tx = {"sender": "alice", "fee": 1}
        h1 = db_pool.add(tx)
        h2 = db_pool.add(tx)
        assert h1 == h2
        assert db_pool.size() == 1

    def test_min_fee_rejected(self, tmp_path):
        pool = DatabaseMempool(str(tmp_path / "fee.db"), min_fee=10)
        with pytest.raises(ValueError, match="below minimum"):
            pool.add({"sender": "alice", "fee": 5})

    def test_max_size_eviction(self, tmp_path):
        pool = DatabaseMempool(str(tmp_path / "evict.db"), max_size=2)
        pool.add({"sender": "a", "fee": 1, "nonce": 1})
        pool.add({"sender": "b", "fee": 5, "nonce": 2})
        pool.add({"sender": "c", "fee": 10, "nonce": 3})
        assert pool.size() == 2
        txs = pool.list_transactions()
        fees = sorted([t.fee for t in txs])
        assert fees == [5, 10]

    def test_drain_by_fee_priority(self, db_pool):
        db_pool.add({"sender": "low", "fee": 1, "nonce": 1})
        db_pool.add({"sender": "high", "fee": 100, "nonce": 2})
        db_pool.add({"sender": "mid", "fee": 50, "nonce": 3})

        drained = db_pool.drain(max_count=2, max_bytes=1_000_000)
        assert len(drained) == 2
        assert drained[0].fee == 100
        assert drained[1].fee == 50
        assert db_pool.size() == 1

    def test_drain_respects_max_count(self, db_pool):
        for i in range(10):
            db_pool.add({"sender": f"s{i}", "fee": i, "nonce": i})
        drained = db_pool.drain(max_count=3, max_bytes=1_000_000)
        assert len(drained) == 3
        assert db_pool.size() == 7

    def test_remove(self, db_pool):
        tx_hash = db_pool.add({"sender": "alice", "fee": 1})
        assert db_pool.size() == 1
        assert db_pool.remove(tx_hash) is True
        assert db_pool.size() == 0
        assert db_pool.remove(tx_hash) is False

    def test_persistence(self, tmp_path):
        db_path = str(tmp_path / "persist.db")
        pool1 = DatabaseMempool(db_path)
        pool1.add({"sender": "alice", "fee": 1})
        pool1.add({"sender": "bob", "fee": 2})
        assert pool1.size() == 2

        # New instance reads same data
        pool2 = DatabaseMempool(db_path)
        assert pool2.size() == 2
        txs = pool2.list_transactions()
        assert len(txs) == 2


class TestCircuitBreaker:
    def test_starts_closed(self):
        from aitbc_chain.consensus.poa import CircuitBreaker
        cb = CircuitBreaker(threshold=3, timeout=1)
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        from aitbc_chain.consensus.poa import CircuitBreaker
        cb = CircuitBreaker(threshold=3, timeout=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        from aitbc_chain.consensus.poa import CircuitBreaker
        cb = CircuitBreaker(threshold=1, timeout=1)
        cb.record_failure()
        assert cb.state == "open"
        assert cb.allow_request() is False
        # Simulate timeout by manipulating last failure time
        cb._last_failure_time = time.time() - 2
        assert cb.state == "half-open"
        assert cb.allow_request() is True

    def test_success_resets(self):
        from aitbc_chain.consensus.poa import CircuitBreaker
        cb = CircuitBreaker(threshold=2, timeout=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        cb.record_success()
        assert cb.state == "closed"
        assert cb.allow_request() is True


class TestInitMempool:
    def test_init_memory(self):
        init_mempool(backend="memory", max_size=50, min_fee=0)
        pool = get_mempool()
        assert isinstance(pool, InMemoryMempool)

    def test_init_database(self, tmp_path):
        db_path = str(tmp_path / "init.db")
        init_mempool(backend="database", db_path=db_path, max_size=50, min_fee=0)
        pool = get_mempool()
        assert isinstance(pool, DatabaseMempool)
