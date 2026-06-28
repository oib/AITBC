"""Parallel block fetcher for multi-peer sync.

Divides a missing block range into sub-ranges, assigns each to a different
peer, fetches in parallel, and merges results deterministically (by block
height). Falls back to sequential fetching from a single peer if peers fail
or no peers are available.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.sync.peer_capability import PeerCapabilityTracker

logger = get_logger(__name__)


class NoPeersAvailableError(RuntimeError):
    """Raised when no peers are available to fetch the requested range."""


class ParallelBlockFetcher:
    """Fetches block ranges from multiple peers in parallel.

    Divides a missing block range into sub-ranges, assigns each to a
    different peer, fetches in parallel, and merges results deterministically
    (by block height). Falls back to sequential if peers fail.

    Usage::

        tracker = PeerCapabilityTracker()
        tracker.register_peer(PeerCapability("p1", "http://p1", (0, 1000)))
        fetcher = ParallelBlockFetcher(tracker, max_peers=4)
        blocks = await fetcher.fetch_range(100, 200, fetch_fn)
    """

    def __init__(
        self,
        tracker: PeerCapabilityTracker,
        max_peers: int = 4,
        timeout: float = 30.0,
    ) -> None:
        self._tracker = tracker
        self._max_peers = max_peers
        self._timeout = timeout

    async def fetch_range(
        self,
        start: int,
        end: int,
        fetch_fn: Callable[[str, int, int], Awaitable[list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        """Fetch blocks [start, end] in parallel from multiple peers.

        Args:
            start: Start block height (inclusive).
            end: End block height (inclusive).
            fetch_fn: Async function ``(rpc_url, range_start, range_end) -> list[blocks]``.
                The first argument is the peer's ``rpc_url`` (not peer_id).

        Returns:
            List of block dicts sorted by height. Deterministic merge:
            if two peers return the same height, the first peer's block wins.

        Raises:
            NoPeersAvailableError: If no peers cover the requested range.
        """
        # select_peers_for_range returns list of (peer_id, sub_range) tuples
        assignments = self._tracker.select_peers_for_range(start, end, max_peers=self._max_peers)
        if not assignments:
            raise NoPeersAvailableError(f"No peers available for range [{start}, {end}]")

        # Build (rpc_url, sub_range) pairs
        url_assignments: list[tuple[str, tuple[int, int]]] = []
        for peer_id, sub_range in assignments:
            peer = self._tracker.get_peer(peer_id)
            if peer is not None:
                url_assignments.append((peer.rpc_url, sub_range))

        if not url_assignments:
            raise NoPeersAvailableError(f"No peers available for range [{start}, {end}]")

        # Single peer — no need for parallel coordination
        if len(url_assignments) == 1:
            rpc_url, (rs, re_) = url_assignments[0]
            return await self._fetch_with_retries(rpc_url, rs, re_, fetch_fn, start, end)

        logger.info("Parallel fetch range [%d, %d] from %d peers", start, end, len(url_assignments))

        # Fetch each sub-range from its assigned peer in parallel
        tasks = {
            asyncio.ensure_future(self._fetch_with_timeout(rpc_url, rs, re_, fetch_fn)): (rpc_url, rs, re_)
            for rpc_url, (rs, re_) in url_assignments
        }
        results: dict[int, dict[str, Any]] = {}
        failed_ranges: list[tuple[int, int]] = []

        done, pending = await asyncio.wait(tasks.keys(), timeout=self._timeout, return_when=asyncio.ALL_COMPLETED)
        for task in pending:
            task.cancel()
            rpc_url, rs, re_ = tasks[task]
            logger.warning("Peer %s timed out for range [%d, %d]", rpc_url, rs, re_)
            failed_ranges.append((rs, re_))

        for task in done:
            rpc_url, rs, re_ = tasks[task]
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "Peer %s failed for range [%d, %d]: %s",
                    rpc_url,
                    rs,
                    re_,
                    exc,
                )
                # Record failure using peer_id (find it from rpc_url)
                fail_peer_id = self._find_peer_id(rpc_url)
                if fail_peer_id:
                    self._tracker.record_failure(fail_peer_id, reason=str(exc))
                failed_ranges.append((rs, re_))
                continue
            for block in task.result():
                height = block.get("height") if block.get("height") is not None else block.get("index")
                if height is None:
                    continue
                if height not in results:
                    results[height] = block
            # Record success using peer_id
            success_peer_id = self._find_peer_id(rpc_url)
            if success_peer_id:
                self._tracker.record_success(success_peer_id, blocks_fetched=re_ - rs + 1)

        # Re-fetch failed sub-ranges from any remaining healthy peer
        for rs, re_ in failed_ranges:
            fallback = self._tracker.select_peers_for_range(rs, re_, max_peers=1)
            if not fallback:
                logger.error("No fallback peer for failed range [%d, %d]", rs, re_)
                continue
            fb_peer_id, _ = fallback[0]
            fb_peer = self._tracker.get_peer(fb_peer_id)
            if fb_peer is None:
                continue
            try:
                blocks = await self._fetch_with_timeout(fb_peer.rpc_url, rs, re_, fetch_fn)
                for block in blocks:
                    height = block.get("height") if block.get("height") is not None else block.get("index")
                    if height is None:
                        continue
                    if height not in results:
                        results[height] = block
                self._tracker.record_success(fb_peer_id, blocks_fetched=re_ - rs + 1)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Fallback peer %s failed for range [%d, %d]: %s",
                    fb_peer.rpc_url,
                    rs,
                    re_,
                    exc,
                )
                self._tracker.record_failure(fb_peer_id, reason=str(exc))

        return [results[h] for h in sorted(results)]

    async def fetch_range_sequential(
        self,
        start: int,
        end: int,
        fetch_fn: Callable[[str, int, int], Awaitable[list[dict[str, Any]]]],
        rpc_url: str,
    ) -> list[dict[str, Any]]:
        """Fallback: fetch from a single peer sequentially."""
        blocks = await self._fetch_with_timeout(rpc_url, start, end, fetch_fn)
        return sorted(blocks, key=lambda b: b.get("height", b.get("index", 0)))

    # --- internals ---

    def _find_peer_id(self, rpc_url: str) -> str | None:
        """Find peer_id by rpc_url."""
        for peer in self._tracker.get_all_peers():
            if peer.rpc_url == rpc_url:
                return peer.peer_id
        return None

    async def _fetch_with_timeout(
        self,
        rpc_url: str,
        rs: int,
        re_: int,
        fetch_fn: Callable[[str, int, int], Awaitable[list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        """Wrap fetch_fn with a timeout."""
        return await asyncio.wait_for(fetch_fn(rpc_url, rs, re_), timeout=self._timeout)

    async def _fetch_with_retries(
        self,
        rpc_url: str,
        start: int,
        end: int,
        fetch_fn: Callable[[str, int, int], Awaitable[list[dict[str, Any]]]],
        full_start: int,
        full_end: int,
    ) -> list[dict[str, Any]]:
        """Fetch from a single peer, with fallback to other peers on failure."""
        peer_id = self._find_peer_id(rpc_url)
        try:
            blocks = await self._fetch_with_timeout(rpc_url, start, end, fetch_fn)
            if peer_id:
                self._tracker.record_success(peer_id, blocks_fetched=end - start + 1)
            return sorted(blocks, key=lambda b: b.get("height", b.get("index", 0)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Primary peer %s failed: %s", rpc_url, exc)
            if peer_id:
                self._tracker.record_failure(peer_id, reason=str(exc))
            # Try fallback peers
            fallbacks = self._tracker.select_peers_for_range(full_start, full_end, max_peers=self._max_peers)
            for fb_peer_id, _ in fallbacks:
                if fb_peer_id == peer_id:
                    continue
                fb_peer = self._tracker.get_peer(fb_peer_id)
                if fb_peer is None:
                    continue
                try:
                    blocks = await self._fetch_with_timeout(fb_peer.rpc_url, start, end, fetch_fn)
                    self._tracker.record_success(fb_peer_id, blocks_fetched=end - start + 1)
                    return sorted(blocks, key=lambda b: b.get("height", b.get("index", 0)))
                except Exception as exc2:  # noqa: BLE001
                    logger.warning("Fallback peer %s failed: %s", fb_peer.rpc_url, exc2)
                    self._tracker.record_failure(fb_peer_id, reason=str(exc2))
            raise
