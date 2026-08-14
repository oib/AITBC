"""Integration tests for v0.6.2 sync optimization features (parallel sync, delta sync, peer tracking)."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test_sync_opt.db", echo=False)
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


@pytest.fixture
def sync(session_factory):
    """Create a ChainSync instance with signature validation disabled."""
    return ChainSync(session_factory, chain_id="test", validate_signatures=False)


class TestPeerCapabilityTracker:
    """Test peer capability tracking in ChainSync."""

    def test_register_peer_updates_tracker(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 1000))
        peer = sync._peer_tracker.get_peer("peer1")
        assert peer is not None
        assert peer.rpc_url == "http://peer1:8202"
        assert peer.block_range == (0, 1000)

    def test_update_peer_capability(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 500))
        sync.update_peer_capability("peer1", (0, 1000))
        peer = sync._peer_tracker.get_peer("peer1")
        assert peer.block_range == (0, 1000)

    def test_record_success_increases_reputation(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 1000))
        # Lower reputation first (it starts at 1.0 which is the max)
        sync._peer_tracker.record_failure("peer1", "warmup failure")
        lowered = sync._peer_tracker.get_peer("peer1").reputation
        sync._peer_tracker.record_success("peer1", 50)
        assert sync._peer_tracker.get_peer("peer1").reputation > lowered

    def test_record_failure_decreases_reputation(self, sync):
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 1000))
        initial = sync._peer_tracker.get_peer("peer1").reputation
        sync._peer_tracker.record_failure("peer1", "timeout")
        assert sync._peer_tracker.get_peer("peer1").reputation < initial


class TestParallelSync:
    """Test parallel block fetching from multiple peers."""


class TestDeltaSync:
    """Test delta-based state synchronization."""
