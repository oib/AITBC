"""Chain bulk sync strategies (sequential and parallel)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from .base_models import Block
from .config import settings
from .logger import get_logger
from .metrics import metrics_registry
from .sync_base import SyncBase
from .sync_divergence import clear_divergence, report_divergence

logger = get_logger(__name__)


class BulkSyncMixin(SyncBase):
    """Fetch and import blocks in bulk from remote peers."""

    # ponytail: Protocol base declares the attributes the concrete ChainSync sets.
    _last_bulk_sync_time: int

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    def _calculate_dynamic_batch_size(self, gap_size: int) -> int:
        """Calculate dynamic batch size based on gap size.

        Strategy:
        - Initial sync gaps (>10,000): Very large batches (500-1000) for maximum throughput
        - Large gaps (1,000-10,000): Accelerated batches (200-500)
        - Medium gaps (500-1,000): Standard batches (100-200)
        - Small gaps (<500): Precision batches (20-100)
        """
        min_batch = getattr(settings, "min_bulk_sync_batch_size", 20)
        max_batch = getattr(settings, "max_bulk_sync_batch_size", 200)
        initial_sync_threshold = getattr(settings, "initial_sync_threshold", 10000)
        initial_sync_max_batch = getattr(settings, "initial_sync_max_batch_size", 1000)
        large_gap_threshold = getattr(settings, "large_gap_threshold", 1000)
        large_gap_max_batch = getattr(settings, "large_gap_max_batch_size", 500)
        if gap_size > initial_sync_threshold:
            return min(gap_size, initial_sync_max_batch)
        elif gap_size > large_gap_threshold:
            return min(200 + (gap_size - large_gap_threshold) // 10, large_gap_max_batch)
        elif gap_size > 500:
            return min(100 + (gap_size - 500) // 5, max_batch)
        elif gap_size > 100:
            return min(50 + (gap_size - 100) // 4, 100)
        else:
            return min(min_batch + gap_size // 2, 50)

    def _get_adaptive_poll_interval(self, gap_size: int) -> float:
        """Get adaptive polling interval based on sync mode.

        Strategy:
        - Initial sync gaps (>10,000): Fast polling (2s) for maximum throughput
        - Large gaps (1,000-10,000): Moderate polling (3s)
        - Medium gaps (500-1,000): Standard polling (5s)
        - Small gaps (<500): Steady-state polling (5s)
        """
        initial_sync_threshold = getattr(settings, "initial_sync_threshold", 10000)
        initial_sync_poll_interval = getattr(settings, "initial_sync_poll_interval", 2.0)
        large_gap_threshold = getattr(settings, "large_gap_threshold", 1000)
        large_gap_poll_interval = getattr(settings, "large_gap_poll_interval", 3.0)
        if gap_size > initial_sync_threshold:
            return initial_sync_poll_interval
        elif gap_size > large_gap_threshold:
            return large_gap_poll_interval
        else:
            return self._poll_interval

    def _get_adaptive_bulk_sync_interval(self, gap_size: int) -> int:
        """Get adaptive bulk sync interval based on sync mode.

        Strategy:
        - Initial sync gaps (>10,000): Frequent bulk sync (10s) for maximum throughput
        - Large gaps (1,000-10,000): Moderate bulk sync (30s)
        - Medium gaps (500-1,000): Standard bulk sync (60s)
        - Small gaps (<500): Steady-state bulk sync (60s)
        """
        initial_sync_threshold = getattr(settings, "initial_sync_threshold", 10000)
        initial_sync_bulk_interval = getattr(settings, "initial_sync_bulk_interval", 10)
        large_gap_threshold = getattr(settings, "large_gap_threshold", 1000)
        large_gap_bulk_interval = getattr(settings, "large_gap_bulk_interval", 30)
        if gap_size > initial_sync_threshold:
            return initial_sync_bulk_interval
        elif gap_size > large_gap_threshold:
            return large_gap_bulk_interval
        else:
            return self._min_bulk_sync_interval

    def _get_sync_mode(self, gap_size: int) -> str:
        """Determine current sync mode based on gap size."""
        initial_sync_threshold = getattr(settings, "initial_sync_threshold", 10000)
        large_gap_threshold = getattr(settings, "large_gap_threshold", 1000)
        if gap_size > initial_sync_threshold:
            return "initial_sync"
        elif gap_size > large_gap_threshold:
            return "large_gap"
        elif gap_size > 500:
            return "medium_gap"
        else:
            return "steady_state"

    async def fetch_blocks_range(self, start: int, end: int, source_url: str) -> list[dict[str, Any]]:
        """Fetch a range of blocks from a source RPC."""
        try:
            resp = await self._client.get(
                f"{source_url}/rpc/blocks-range",
                params={"start": start, "end": end, "chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "blocks" in data:
                return data["blocks"]  # type: ignore[no-any-return]
            else:
                logger.error("Unexpected blocks-range response", extra={"data": data})
                return []
        except Exception as e:
            logger.error("Failed to fetch blocks range", extra={"start": start, "end": end, "error": str(e)})
            return []

    async def bulk_import_from(self, source_url: str) -> int:
        """Import blocks from a remote source via RPC."""
        self._logger.info("Starting bulk import from source: %s", source_url)
        if source_url and (not source_url.startswith("http://")) and (not source_url.startswith("https://")):
            source_url = f"http://{source_url}"
            self._logger.info("Added http:// prefix to source URL: %s", source_url)
        if not source_url:
            self._logger.error("Source URL is empty or None")
            return 0
        with self._session_factory() as session:
            local_head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
            ).first()
            local_height = local_head.height if local_head else -1
            logger.info(
                "Bulk sync local head: chain_id=%s, height=%s, hash=%s",
                self._chain_id,
                local_height,
                local_head.hash if local_head else None,
            )
        try:
            resp = await self._client.get(f"{source_url}/rpc/head", params={"chain_id": self._chain_id})
            resp.raise_for_status()
            remote_head = resp.json()
            remote_height = remote_head.get("height", -1)
        except Exception as e:
            logger.error("Failed to fetch remote head", extra={"source_url": source_url, "error": str(e)})
            return 0
        # Register/update peer capability for parallel sync
        peer_id = source_url  # In v0.6.2, peer_id IS the URL
        self.register_sync_peer(peer_id, source_url, (0, remote_height), has_state=True)
        if remote_height <= local_height:
            # Not necessarily up to date: a follower whose peer was reset to genesis is *ahead* of
            # that peer on a chain the peer no longer has. Heights alone cannot tell the two apart,
            # so compare the hash we hold at the peer's head height (V23-90).
            divergence = self.detect_divergence(source_url, remote_height, remote_head.get("hash", ""))
            if divergence is not None:
                report_divergence(self._chain_id, divergence)
                return 0
            clear_divergence(self._chain_id)
            logger.info("Already up to date", extra={"local_height": local_height, "remote_height": remote_height})
            return 0
        gap_size = remote_height - local_height
        sync_mode = self._get_sync_mode(gap_size)
        dynamic_batch_size = self._calculate_dynamic_batch_size(gap_size)
        adaptive_bulk_interval = self._get_adaptive_bulk_sync_interval(gap_size)
        adaptive_poll_interval = self._get_adaptive_poll_interval(gap_size)
        current_time = time.time()
        time_since_last_sync = current_time - self._last_bulk_sync_time
        if time_since_last_sync < adaptive_bulk_interval:
            logger.warning(
                "Bulk sync rate limited",
                extra={
                    "time_since_last_sync": time_since_last_sync,
                    "min_interval": adaptive_bulk_interval,
                    "sync_mode": sync_mode,
                },
            )
            return 0
        logger.info(
            "Starting bulk import",
            extra={
                "local_height": local_height,
                "remote_height": remote_height,
                "gap_size": gap_size,
                "batch_size": dynamic_batch_size,
                "sync_mode": sync_mode,
                "bulk_interval": adaptive_bulk_interval,
                "poll_interval": adaptive_poll_interval,
            },
        )
        metrics_registry.set_gauge(f"sync_mode_{sync_mode}", 1.0)
        metrics_registry.set_gauge("sync_gap_size", float(gap_size))
        metrics_registry.set_gauge("sync_batch_size", float(dynamic_batch_size))
        # Check if parallel sync is enabled
        use_parallel = getattr(settings, "sync_parallel_enabled", False) and len(self._peer_tracker.get_all_peers()) > 1
        start_height = local_height + 1
        if use_parallel:
            imported = await self._parallel_bulk_import(
                start_height, remote_height, source_url, dynamic_batch_size, adaptive_poll_interval
            )
        else:
            imported = await self._sequential_bulk_import(
                start_height, remote_height, source_url, dynamic_batch_size, adaptive_poll_interval
            )
        logger.info(
            "Bulk import completed", extra={"imported": imported, "final_height": remote_height, "sync_mode": sync_mode}
        )
        sync_duration = time.time() - current_time
        metrics_registry.observe("sync_bulk_duration_seconds", sync_duration)
        if imported > 0:
            sync_rate = imported / sync_duration
            metrics_registry.observe("sync_blocks_per_second", sync_rate)
        metrics_registry.set_gauge("sync_chain_height", float(remote_height))
        self._last_bulk_sync_time = int(current_time)
        return imported

    async def _sequential_bulk_import(
        self, start_height: int, end_height: int, source_url: str, batch_size: int, poll_interval: float
    ) -> int:
        """Fetch blocks sequentially from a single peer (existing path)."""
        imported = 0
        current = start_height
        while current <= end_height:
            batch_end = min(current + batch_size - 1, end_height)
            batch = await self.fetch_blocks_range(current, batch_end, source_url)
            if not batch:
                logger.warning("No blocks returned for range", extra={"start": current, "end": batch_end})
                break
            for block_data in batch:
                result = self.import_block(
                    block_data, transactions=block_data.get("transactions"), skip_state_root_validation=True
                )
                if result.accepted:
                    imported += 1
                    logger.info(
                        "Block imported via pull sync",
                        extra={
                            "height": block_data.get("height"),
                            "hash": block_data.get("hash"),
                            "sync_mode": "pull",
                            "progress": f"{imported}/{end_height - start_height + 1}",
                        },
                    )
                else:
                    logger.warning(
                        "Block import failed during bulk at height %s: %s",
                        block_data.get("height"),
                        result.reason,
                        extra={"height": block_data.get("height"), "reason": result.reason},
                    )
                    return imported
            current = batch_end + 1
            await asyncio.sleep(poll_interval)
        return imported

    async def _parallel_bulk_import(
        self, start_height: int, end_height: int, source_url: str, batch_size: int, poll_interval: float
    ) -> int:
        """Fetch blocks in parallel from multiple peers."""
        max_peers = getattr(settings, "sync_parallel_max_peers", 4)
        timeout = getattr(settings, "sync_parallel_timeout", 30.0)

        # Select peers for the range
        assignments = self._peer_tracker.select_peers_for_range(start_height, end_height, max_peers=max_peers)
        if not assignments:
            # No peers available, fall back to sequential
            return await self._sequential_bulk_import(start_height, end_height, source_url, batch_size, poll_interval)

        self._logger.info("Parallel sync: %d peers for range %d-%d", len(assignments), start_height, end_height)

        # Fetch from each peer in parallel
        async def fetch_from_peer(peer_id: str, sub_range: tuple[int, int]) -> list[dict[str, Any]]:
            try:
                # In v0.6.2, peer_id IS the URL
                blocks = await asyncio.wait_for(
                    self.fetch_blocks_range(sub_range[0], sub_range[1], peer_id),
                    timeout=timeout,
                )
                self._peer_tracker.record_success(peer_id, len(blocks))
                return blocks
            except Exception as e:
                self._logger.warning("Peer %s failed: %s", peer_id, e)
                self._peer_tracker.record_failure(peer_id, str(e))
                return []

        results = await asyncio.gather(*[fetch_from_peer(pid, sr) for pid, sr in assignments])

        # Merge results: concatenate, sort by height, deduplicate by hash
        all_blocks: list[dict[str, Any]] = []
        for blocks in results:
            all_blocks.extend(blocks)
        all_blocks.sort(key=lambda b: b.get("height", 0))

        # Deduplicate by hash (keep first occurrence)
        seen_hashes: set[str] = set()
        unique_blocks: list[dict[str, Any]] = []
        for block in all_blocks:
            h = block.get("hash", "")
            if h and h not in seen_hashes:
                seen_hashes.add(h)
                unique_blocks.append(block)

        # Check for conflicts (same height, different hash)
        height_map: dict[int, str] = {}
        conflicts: list[int] = []
        for block in unique_blocks:
            h = block.get("height", -1)
            hash_val = block.get("hash", "")
            if h in height_map and height_map[h] != hash_val:
                conflicts.append(h)
            else:
                height_map[h] = hash_val

        if conflicts:
            self._logger.warning("Block conflicts at heights %s, falling back to sequential", conflicts)
            return await self._sequential_bulk_import(start_height, end_height, source_url, batch_size, poll_interval)

        # Import merged block list
        imported = 0
        for block_data in unique_blocks:
            result = self.import_block(
                block_data, transactions=block_data.get("transactions"), skip_state_root_validation=True
            )
            if result.accepted:
                imported += 1
            else:
                self._logger.warning("Block import failed at height %s: %s", block_data.get("height"), result.reason)
                return imported

        return imported
