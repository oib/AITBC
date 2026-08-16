"""Unit tests for aitbc.sync.parallel_fetcher (A2)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from aitbc.sync.parallel_fetcher import NoPeersAvailableError, ParallelBlockFetcher
from aitbc.sync.peer_capability import PeerCapability, PeerCapabilityTracker

_FetchFn = Callable[[str, int, int], Awaitable[list[dict[str, Any]]]]


def _make_block(height: int, data: str = "block") -> dict[str, Any]:
    return {"height": height, "data": data}


async def _fetch_all(peer_url: str, start: int, end: int) -> list[dict[str, Any]]:
    """Mock fetch_fn that returns all blocks in range."""
    await asyncio.sleep(0)  # cooperative
    return [_make_block(h) for h in range(start, end + 1)]


async def _fetch_failing(peer_url: str, start: int, end: int) -> list[dict[str, Any]]:
    """Mock fetch_fn that always raises."""
    raise RuntimeError(f"peer {peer_url} failed")


def _fetch_fail_for_peer(failing_url: str) -> _FetchFn:
    """Return a fetch_fn that fails for the given peer URL."""

    async def fetch_fn(peer_url: str, start: int, end: int) -> list[dict[str, Any]]:
        if peer_url == failing_url:
            raise RuntimeError(f"peer {peer_url} failed")
        return [_make_block(h) for h in range(start, end + 1)]

    return fetch_fn


def _make_tracker(n_peers: int, block_range: tuple[int, int] = (0, 1000)) -> PeerCapabilityTracker:
    """Create a tracker with n_peers registered."""
    tracker = PeerCapabilityTracker()
    for i in range(n_peers):
        tracker.register_peer(
            PeerCapability(
                peer_id=f"peer{i}",
                rpc_url=f"http://peer{i}:8202",
                block_range=block_range,
                latency_ms=10.0 * i,
            )
        )
    return tracker


class TestFetchRangeParallel:
    @pytest.mark.asyncio
    async def test_fetch_range_parallel(self) -> None:
        """4 peers, 100 blocks, verify all fetched."""
        tracker = _make_tracker(4)
        fetcher = ParallelBlockFetcher(tracker, max_peers=4)
        blocks = await fetcher.fetch_range(0, 99, _fetch_all)
        assert len(blocks) == 100
        heights = [b["height"] for b in blocks]
        assert heights == list(range(0, 100))

    @pytest.mark.asyncio
    async def test_fetch_range_single_peer(self) -> None:
        """Single peer → no splitting, just fetch."""
        tracker = _make_tracker(1)
        fetcher = ParallelBlockFetcher(tracker, max_peers=4)
        blocks = await fetcher.fetch_range(0, 9, _fetch_all)
        assert len(blocks) == 10

    @pytest.mark.asyncio
    async def test_fetch_range_no_peers(self) -> None:
        """No peers available → NoPeersAvailableError."""
        tracker = PeerCapabilityTracker()
        fetcher = ParallelBlockFetcher(tracker)
        with pytest.raises(NoPeersAvailableError):
            await fetcher.fetch_range(0, 100, _fetch_all)

    @pytest.mark.asyncio
    async def test_fetch_range_no_peer_covers_range(self) -> None:
        """Peer doesn't cover the requested range → NoPeersAvailableError."""
        tracker = PeerCapabilityTracker()
        tracker.register_peer(PeerCapability(peer_id="p1", rpc_url="http://p1", block_range=(0, 50)))
        fetcher = ParallelBlockFetcher(tracker)
        with pytest.raises(NoPeersAvailableError):
            await fetcher.fetch_range(60, 100, _fetch_all)

    @pytest.mark.asyncio
    async def test_fetch_range_peer_failure_fallback(self) -> None:
        """One peer fails, blocks still fetched from fallback."""
        tracker = _make_tracker(2)
        fetcher = ParallelBlockFetcher(tracker, max_peers=2)
        fetch_fn = _fetch_fail_for_peer("http://peer0:8202")
        blocks = await fetcher.fetch_range(0, 9, fetch_fn)
        # peer0 fails, peer1 should cover the failed sub-range as fallback
        assert len(blocks) == 10

    @pytest.mark.asyncio
    async def test_fetch_range_all_peers_fail(self) -> None:
        """All peers fail → raises."""
        tracker = _make_tracker(1)
        fetcher = ParallelBlockFetcher(tracker, max_peers=1)
        with pytest.raises(RuntimeError):
            await fetcher.fetch_range(0, 9, _fetch_failing)

    @pytest.mark.asyncio
    async def test_fetch_range_deterministic_merge(self) -> None:
        """All blocks present and sorted by height after parallel fetch."""
        tracker = _make_tracker(2)
        fetcher = ParallelBlockFetcher(tracker, max_peers=2)
        blocks = await fetcher.fetch_range(0, 9, _fetch_all)
        assert len(blocks) == 10
        heights = [b["height"] for b in blocks]
        assert sorted(heights) == list(range(0, 10))


class TestFetchRangeSequential:
    @pytest.mark.asyncio
    async def test_fetch_range_sequential(self) -> None:
        """Fallback path: fetch from a single peer sequentially."""
        tracker = _make_tracker(1)
        fetcher = ParallelBlockFetcher(tracker)
        blocks = await fetcher.fetch_range_sequential(0, 9, _fetch_all, "http://peer0:8202")
        assert len(blocks) == 10
        heights = [b["height"] for b in blocks]
        assert heights == list(range(0, 10))


class TestReputationTracking:
    @pytest.mark.asyncio
    async def test_success_increases_reputation(self) -> None:
        """Successful fetch increases peer reputation."""
        tracker = _make_tracker(1)
        # Set initial reputation below max so it can increase
        peer = tracker.get_peer("peer0")
        peer.reputation = 0.5
        initial_rep = peer.reputation
        fetcher = ParallelBlockFetcher(tracker, max_peers=1)
        await fetcher.fetch_range(0, 9, _fetch_all)
        assert tracker.get_peer("peer0").reputation > initial_rep

    @pytest.mark.asyncio
    async def test_failure_decreases_reputation(self) -> None:
        """Failed fetch decreases peer reputation."""
        tracker = _make_tracker(2)
        peer = tracker.get_peer("peer0")
        initial_rep = peer.reputation
        fetcher = ParallelBlockFetcher(tracker, max_peers=2)
        fetch_fn = _fetch_fail_for_peer("http://peer0:8202")
        await fetcher.fetch_range(0, 9, fetch_fn)
        assert tracker.get_peer("peer0").reputation < initial_rep
