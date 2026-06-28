"""Integration tests for v0.6.2 sync optimization features (parallel sync, delta sync, peer tracking)."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aitbc.sync import (
    AccountChange,
    StateDiff,
    encode_state_diff,
)
from aitbc_chain.models import Account
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test_sync_opt.db", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


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

    @pytest.mark.asyncio
    async def test_parallel_sync_divides_range_evenly(self, sync):
        """Verify that parallel sync divides the range across peers."""
        # Register 4 peers
        for i in range(4):
            sync.register_sync_peer(f"peer{i}", f"http://peer{i}:8202", (0, 1000))

        assignments = sync._peer_tracker.select_peers_for_range(1, 100, max_peers=4)
        assert len(assignments) == 4
        # Verify ranges cover 1-100
        all_ranges = [r for _, r in assignments]
        assert all_ranges[0][0] == 1
        assert all_ranges[-1][1] == 100

    @pytest.mark.asyncio
    async def test_parallel_sync_merges_results_by_height(self, sync):
        """Verify that parallel sync merges blocks sorted by height."""

        # Mock fetch_blocks_range to return blocks for each peer
        async def mock_fetch(start, end, source_url):
            blocks = []
            for h in range(start, end + 1):
                blocks.append(
                    {
                        "height": h,
                        "hash": f"0x{h:064d}",
                        "parent_hash": f"0x{h - 1:064d}",
                        "proposer": "p",
                        "timestamp": "2026-01-01T00:00:00",
                    }
                )
            return blocks

        sync.fetch_blocks_range = mock_fetch

        # Register 2 peers
        sync.register_sync_peer("peer0", "http://peer0:8202", (0, 100))
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 100))

        # Mock import_block to just count accepted
        sync.import_block = lambda block_data, skip_state_root_validation=False: MagicMock(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="ok"
        )

        result = await sync._parallel_bulk_import(1, 10, "http://peer0:8202", 10, 0.0)
        # Should have imported 10 blocks
        assert result == 10

    @pytest.mark.asyncio
    async def test_parallel_sync_handles_peer_failure(self, sync):
        """Verify that parallel sync continues when a peer fails."""

        async def mock_fetch(start, end, source_url):
            if "peer1" in source_url:
                raise Exception("Connection refused")
            blocks = []
            for h in range(start, end + 1):
                blocks.append(
                    {
                        "height": h,
                        "hash": f"0x{h:064d}",
                        "parent_hash": f"0x{h - 1:064d}",
                        "proposer": "p",
                        "timestamp": "2026-01-01T00:00:00",
                    }
                )
            return blocks

        sync.fetch_blocks_range = mock_fetch
        sync.import_block = lambda block_data, skip_state_root_validation=False: MagicMock(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="ok"
        )

        sync.register_sync_peer("peer0", "http://peer0:8202", (0, 100))
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 100))

        result = await sync._parallel_bulk_import(1, 10, "http://peer0:8202", 10, 0.0)
        # peer0 should have fetched some blocks even though peer1 failed
        assert result > 0

    @pytest.mark.asyncio
    async def test_parallel_sync_falls_back_to_sequential(self, sync):
        """Verify that parallel sync falls back to sequential with one peer."""

        async def mock_fetch(start, end, source_url):
            blocks = []
            for h in range(start, end + 1):
                blocks.append(
                    {
                        "height": h,
                        "hash": f"0x{h:064d}",
                        "parent_hash": f"0x{h - 1:064d}",
                        "proposer": "p",
                        "timestamp": "2026-01-01T00:00:00",
                    }
                )
            return blocks

        sync.fetch_blocks_range = mock_fetch
        sync.import_block = lambda block_data, skip_state_root_validation=False: MagicMock(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="ok"
        )

        # Only one peer — select_peers_for_range returns 1 assignment
        sync.register_sync_peer("peer0", "http://peer0:8202", (0, 100))

        result = await sync._parallel_bulk_import(1, 5, "http://peer0:8202", 5, 0.0)
        assert result == 5

    @pytest.mark.asyncio
    async def test_parallel_sync_conflict_resolution(self, sync):
        """Verify that conflicting blocks trigger fallback to sequential."""

        async def mock_fetch(start, end, source_url):
            blocks = []
            for h in range(start, end + 1):
                # Different hashes for different peers at same height
                peer_num = source_url[-1]
                blocks.append(
                    {
                        "height": h,
                        "hash": f"0x{peer_num}{h:063d}",
                        "parent_hash": f"0x{h - 1:064d}",
                        "proposer": "p",
                        "timestamp": "2026-01-01T00:00:00",
                    }
                )
            return blocks

        sync.fetch_blocks_range = mock_fetch
        sync.import_block = lambda block_data, skip_state_root_validation=False: MagicMock(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="ok"
        )

        sync.register_sync_peer("peer0", "http://peer0:8202", (0, 100))
        sync.register_sync_peer("peer1", "http://peer1:8202", (0, 100))

        # With conflicting hashes, should fall back to sequential and still import
        result = await sync._parallel_bulk_import(1, 10, "http://peer0:8202", 10, 0.0)
        # Sequential fallback should succeed
        assert result > 0


class TestDeltaSync:
    """Test delta-based state synchronization."""

    @pytest.mark.asyncio
    async def test_delta_sync_applies_only_changed_accounts(self, sync, session_factory):
        """Verify that delta sync applies only changed accounts."""
        diff = StateDiff(
            from_height=10,
            to_height=20,
            changes=[
                AccountChange(address="addr1", old_balance=100, new_balance=150, old_nonce=5, new_nonce=6),
                AccountChange(address="addr2", old_balance=0, new_balance=200, old_nonce=0, new_nonce=1, is_new=True),
            ],
            from_state_root="root_a",
            to_state_root="root_b",
        )
        encoded = base64.b64encode(encode_state_diff(diff)).decode()

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {"diff": encoded}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        sync._client = mock_client

        # Mock state root computation to match
        with patch("aitbc_chain.state.state_root_utils.compute_state_root_full", return_value="root_b"):
            with patch("aitbc_chain.sync.settings.sync_delta_enabled", True):
                result = await sync.delta_sync_from("http://peer:8202", 10, 20)

        assert result["mode"] == "delta"
        assert result["synced"] == 2

    @pytest.mark.asyncio
    async def test_delta_sync_falls_back_when_too_large(self, sync, session_factory):
        """Verify that delta sync falls back to full sync when diff is too large."""
        # Seed an account so full_state_size > 0 (required for is_too_large to trigger)
        with session_factory() as session:
            session.add(Account(chain_id="test", address="existing", balance=100, nonce=0))
            session.commit()

        # Create a large diff
        changes = [
            AccountChange(address=f"addr{i:04d}", old_balance=100, new_balance=200, old_nonce=5, new_nonce=6)
            for i in range(100)
        ]
        diff = StateDiff(
            from_height=10,
            to_height=20,
            changes=changes,
            from_state_root="root_a",
            to_state_root="root_b",
        )
        encoded = base64.b64encode(encode_state_diff(diff)).decode()

        mock_response = MagicMock()
        mock_response.json.return_value = {"diff": encoded}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        sync._client = mock_client

        # Mock sync_state_from to verify fallback
        sync.sync_state_from = AsyncMock(return_value={"synced": 0, "mode": "full"})

        with patch("aitbc_chain.sync.settings.sync_delta_enabled", True):
            with patch("aitbc_chain.sync.settings.sync_delta_threshold", 0.01):  # Very low threshold
                result = await sync.delta_sync_from("http://peer:8202", 10, 20)

        # Should have fallen back to full sync
        assert result["mode"] == "full"

    @pytest.mark.asyncio
    async def test_delta_sync_falls_back_when_too_many_blocks(self, sync):
        """Verify that delta sync falls back when gap exceeds max_blocks."""
        with patch("aitbc_chain.sync.settings.sync_delta_enabled", True):
            with patch("aitbc_chain.sync.settings.sync_delta_max_blocks", 10):
                sync.sync_state_from = AsyncMock(return_value={"synced": 0, "mode": "full"})
                result = await sync.delta_sync_from("http://peer:8202", 10, 100)  # gap=90 > 10

        assert result["mode"] == "full"

    @pytest.mark.asyncio
    async def test_delta_sync_falls_back_when_disabled(self, sync):
        """Verify that delta sync falls back to full sync when disabled."""
        sync.sync_state_from = AsyncMock(return_value={"synced": 0, "mode": "full"})
        with patch("aitbc_chain.sync.settings.sync_delta_enabled", False):
            result = await sync.delta_sync_from("http://peer:8202", 10, 20)
        assert result["mode"] == "full"

    @pytest.mark.asyncio
    async def test_delta_sync_verifies_state_root(self, sync):
        """Verify that delta sync checks state root and falls back on mismatch."""
        diff = StateDiff(
            from_height=10,
            to_height=20,
            changes=[AccountChange(address="addr1", old_balance=100, new_balance=150, old_nonce=5, new_nonce=6)],
            from_state_root="root_a",
            to_state_root="expected_root",
        )
        encoded = base64.b64encode(encode_state_diff(diff)).decode()

        mock_response = MagicMock()
        mock_response.json.return_value = {"diff": encoded}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        sync._client = mock_client

        # Mock state root to return a MISMATCH
        with patch("aitbc_chain.state.state_root_utils.compute_state_root_full", return_value="wrong_root"):
            with patch("aitbc_chain.sync.settings.sync_delta_enabled", True):
                sync.sync_state_from = AsyncMock(return_value={"synced": 0, "mode": "full"})
                result = await sync.delta_sync_from("http://peer:8202", 10, 20)

        # Should fall back to full sync due to mismatch
        assert result["mode"] == "full"
