"""Chain synchronization with conflict resolution, signature validation, and metrics."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlmodel import Session, select

from aitbc.parallel import DependencyGraph, ParallelExecutor
from aitbc.sync import PeerCapability, PeerCapabilityTracker

from .base_models import Account, Block
from .base_models import Transaction as ChainTransaction
from .config import settings
from .logger import get_logger
from .metrics import metrics_registry
from .state.merkle_patricia_trie import StateManager
from .state.pure_state_transition import (
    StateDelta,
    apply_delta_to_map,
    apply_deltas_to_db,
    compute_state_delta,
    extract_read_write_sets,
)
from .state.state_transition import get_state_transition

logger = get_logger(__name__)


@dataclass
class ImportResult:
    accepted: bool
    height: int
    block_hash: str
    reason: str
    reorged: bool = False
    reorg_depth: int = 0


class ProposerSignatureValidator:
    """Validates proposer signatures on imported blocks."""

    def __init__(self, trusted_proposers: list[str] | None = None) -> None:
        self._trusted = set(trusted_proposers or [])

    @property
    def trusted_proposers(self) -> set[str]:
        return self._trusted

    def add_trusted(self, proposer_id: str) -> None:
        self._trusted.add(proposer_id)

    def remove_trusted(self, proposer_id: str) -> None:
        self._trusted.discard(proposer_id)

    def validate_block_signature(self, block_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate that a block was produced by a trusted proposer.

        Returns (is_valid, reason).
        """
        proposer = block_data.get("proposer", "")
        block_hash = block_data.get("hash", "")
        block_data.get("height", -1)
        if not proposer:
            return (False, "Missing proposer field")
        if not block_hash:
            return (False, f"Invalid block hash format: {block_hash}")
        if not block_hash.startswith("0x"):
            block_hash = f"0x{block_hash}"
        if self._trusted and proposer not in self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return (False, f"Proposer '{proposer}' not in trusted set")
        expected_fields = ["height", "parent_hash", "timestamp"]
        for field in expected_fields:
            if field not in block_data:
                return (False, f"Missing required field: {field}")
        hash_hex = block_hash[2:]
        if len(hash_hex) != 64:
            return (False, f"Invalid hash length: {len(hash_hex)}")
        try:
            int(hash_hex, 16)
        except ValueError:
            return (False, f"Invalid hex in hash: {hash_hex}")
        metrics_registry.increment("sync_signature_validated_total")
        return (True, "Valid")


class ChainSync:
    """Handles block import with conflict resolution for divergent chains."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        chain_id: str = "",
        max_reorg_depth: int = 10,
        validator: ProposerSignatureValidator | None = None,
        validate_signatures: bool = True,
        batch_size: int = 50,
        poll_interval: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._chain_id = chain_id
        self._logger = get_logger(__name__)
        self._max_reorg_depth = max_reorg_depth
        self._validator = validator or ProposerSignatureValidator()
        self._validate_signatures = validate_signatures
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._client = httpx.AsyncClient(timeout=10.0)
        self._last_bulk_sync_time = 0
        self._min_bulk_sync_interval = getattr(settings, "min_bulk_sync_interval", 60)
        self._rejection_counts: dict[str, int] = {}
        self._peer_tracker = PeerCapabilityTracker()

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    def register_sync_peer(self, peer_id: str, rpc_url: str, block_range: tuple[int, int], has_state: bool = True) -> None:
        """Register a peer for sync."""
        self._peer_tracker.register_peer(
            PeerCapability(
                peer_id=peer_id,
                rpc_url=rpc_url,
                block_range=block_range,
                has_state=has_state,
            )
        )

    def update_peer_capability(self, peer_id: str, block_range: tuple[int, int]) -> None:
        """Update a peer's block range after fetching remote head."""
        peer = self._peer_tracker.get_peer(peer_id)
        if peer:
            peer.block_range = block_range
            peer.last_updated = time.time()

    def _validate_genesis_metadata(self, block_data: dict[str, Any], session: Session) -> tuple[bool, str]:
        """Validate genesis block metadata by computing expected state root from allocations.

        Args:
            block_data: Block data dictionary
            session: Database session

        Returns:
            Tuple of (is_valid, reason)
        """
        try:
            metadata_str = block_data.get("block_metadata")
            if not metadata_str:
                return (False, "Genesis block missing block_metadata")
            metadata = json.loads(metadata_str)
            allocations = metadata.get("allocations", [])
            if not allocations:
                return (False, "Genesis block metadata missing allocations")
            state_manager = StateManager()
            temp_accounts: dict[str, Account] = {}
            for alloc in allocations:
                address = alloc.get("address")
                balance = alloc.get("balance", 0)
                if address:
                    temp_accounts[address] = Account(chain_id="", address=address, balance=balance, nonce=0)
            computed_root = state_manager.compute_state_root(temp_accounts)
            expected_root_hex = block_data.get("state_root", "")
            try:
                expected_root = bytes.fromhex(expected_root_hex.replace("0x", ""))
            except ValueError:
                return (False, f"Invalid state_root format: {expected_root_hex}")
            if computed_root != expected_root:
                return (False, f"State root mismatch: computed {computed_root.hex()}, expected {expected_root.hex()}")
            return (True, "Valid")
        except json.JSONDecodeError as e:
            return (False, f"Invalid JSON in block_metadata: {e}")
        except Exception as e:
            return (False, f"Genesis metadata validation error: {e}")

    def _track_rejection(self, chain_id: str) -> None:
        """Track a state root rejection for the given chain."""
        self._rejection_counts[chain_id] = self._rejection_counts.get(chain_id, 0) + 1

    def _reset_rejection_counter(self, chain_id: str) -> None:
        """Reset rejection counter on successful block import."""
        if chain_id in self._rejection_counts:
            del self._rejection_counts[chain_id]

    def _check_and_trigger_resync(self, chain_id: str) -> bool:
        """Check if rejection threshold reached and trigger auto re-sync.

        Returns:
            True if re-sync was triggered, False otherwise
        """
        if not settings.auto_resync_enabled:
            return False
        threshold = settings.auto_resync_after_rejections
        current_count = self._rejection_counts.get(chain_id, 0)
        if current_count >= threshold:
            logger.warning(
                "State root rejection threshold reached (%s/%s), triggering auto re-sync for chain %s",
                current_count,
                threshold,
                chain_id,
            )
            source_url = settings.auto_resync_source_url or settings.default_peer_rpc_url
            if source_url:
                try:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    imported = loop.run_until_complete(self.bulk_import_from(source_url))
                    logger.info("Auto re-sync completed: %s blocks imported", imported)
                    self._reset_rejection_counter(chain_id)
                    return True
                except Exception as e:
                    logger.error("Auto re-sync failed: %s", e)
            else:
                logger.warning("No source URL available for auto re-sync")
        return False

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
            return min(500 + (gap_size - initial_sync_threshold) // 20, initial_sync_max_batch)
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
                result = self.import_block(block_data, skip_state_root_validation=True)
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
            result = self.import_block(block_data, skip_state_root_validation=True)
            if result.accepted:
                imported += 1
            else:
                self._logger.warning("Block import failed at height %s: %s", block_data.get("height"), result.reason)
                return imported

        return imported

    async def sync_state_from(self, source_url: str) -> dict[str, Any]:
        """Pull account state snapshot from a peer and reconcile local accounts.

        Creates missing accounts and corrects balances/nonces to match
        the peer's state root.  Does NOT delete accounts that exist locally
        but not on the peer (those may be from local transactions).
        """
        self._logger.info("Starting state sync from %s", source_url)
        try:
            resp = await self._client.get(
                f"{source_url}/rpc/state/snapshot",
                params={"chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self._logger.error("Failed to fetch state snapshot: %s", e)
            return {"synced": 0, "error": str(e)}

        remote_accounts = data.get("accounts", [])
        remote_root = data.get("state_root", "")
        self._logger.info(
            "State snapshot: %s accounts, state_root=%s",
            len(remote_accounts),
            remote_root,
        )

        created = 0
        updated = 0
        with self._session_factory() as session:
            # Batch-fetch all existing accounts for the chain in one query
            # (eliminates the N+1 per-account session.get() lookup).
            existing_accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()
            account_map: dict[str, Account] = {acc.address: acc for acc in existing_accounts}
            for acct_data in remote_accounts:
                addr = acct_data["address"]
                balance = acct_data["balance"]
                nonce = acct_data["nonce"]
                existing = account_map.get(addr)
                if existing is None:
                    new_account = Account(
                        chain_id=self._chain_id,
                        address=addr,
                        balance=balance,
                        nonce=nonce,
                    )
                    session.add(new_account)
                    account_map[addr] = new_account
                    created += 1
                elif existing.balance != balance or existing.nonce != nonce:
                    existing.balance = balance
                    existing.nonce = nonce
                    updated += 1
            session.commit()

        # Verify state root matches now — full recompute (all accounts synced)
        from .state.state_root_utils import compute_state_root_full

        with self._session_factory() as session:
            computed_hex = compute_state_root_full(session, self._chain_id)
            if computed_hex is None:
                computed_hex = "0x" + "\x00" * 32

        match = computed_hex == remote_root
        self._logger.info(
            "State sync complete: created=%s, updated=%s, local_root=%s, remote_root=%s, match=%s",
            created,
            updated,
            computed_hex,
            remote_root,
            match,
        )
        return {
            "synced": created + updated,
            "created": created,
            "updated": updated,
            "local_state_root": computed_hex,
            "remote_state_root": remote_root,
            "match": match,
        }

    async def delta_sync_from(self, source_url: str, from_height: int, to_height: int) -> dict[str, Any]:
        """Sync state delta from a peer (only changed accounts).

        Feature-flagged via settings.sync_delta_enabled. Falls back to
        full state sync (sync_state_from) when:
        - delta is too large (> sync_delta_threshold * full_state_size)
        - gap exceeds sync_delta_max_blocks
        - peer doesn't support delta endpoint
        - state root verification fails
        """
        if not getattr(settings, "sync_delta_enabled", False):
            return await self.sync_state_from(source_url)

        max_blocks = getattr(settings, "sync_delta_max_blocks", 100)
        if to_height - from_height > max_blocks:
            self._logger.info("Delta sync gap too large (%d > %d), using full sync", to_height - from_height, max_blocks)
            return await self.sync_state_from(source_url)

        self._logger.info("Starting delta sync from %s, heights %d -> %d", source_url, from_height, to_height)
        try:
            resp = await self._client.post(
                f"{source_url}/rpc/state/delta",
                json={"from_height": from_height, "to_height": to_height, "chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self._logger.warning("Delta sync endpoint failed (%s), falling back to full sync", e)
            return await self.sync_state_from(source_url)

        # The response contains an encoded StateDiff
        encoded_diff = data.get("diff")
        if not encoded_diff:
            self._logger.warning("No diff in delta sync response, falling back to full sync")
            return await self.sync_state_from(source_url)

        # Decode the StateDiff
        try:
            from aitbc.sync import apply_state_diff, decode_state_diff

            # The encoded diff may be base64-encoded bytes
            import base64

            diff_bytes = base64.b64decode(encoded_diff) if isinstance(encoded_diff, str) else encoded_diff
            diff = decode_state_diff(diff_bytes)
        except Exception as e:
            self._logger.error("Failed to decode state diff: %s", e)
            return await self.sync_state_from(source_url)

        # Check if delta is too large
        threshold = getattr(settings, "sync_delta_threshold", 0.5)
        # Estimate full state size from current account count
        from sqlalchemy import func as sqlfunc

        with self._session_factory() as session:
            count_result = session.exec(
                select(sqlfunc.count()).select_from(Account).where(Account.chain_id == self._chain_id)
            ).first()
            total_accounts = count_result or 0
        full_state_size = total_accounts * 100  # rough estimate
        if diff.is_too_large(full_state_size, threshold=threshold):
            self._logger.info(
                "Delta too large (%d bytes > %d threshold), using full sync",
                diff.size_bytes(),
                int(threshold * full_state_size),
            )
            return await self.sync_state_from(source_url)

        # Apply delta to local state
        with self._session_factory() as session:
            existing_accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()
            account_map: dict[str, Any] = {acc.address: acc for acc in existing_accounts}
            changed = apply_state_diff(diff, account_map)
            # Handle new accounts (created as dicts by apply_state_diff)
            for addr in changed:
                acc = account_map.get(addr)
                if acc is not None and isinstance(acc, dict):
                    # New account created as dict — convert to Account model
                    new_acc = Account(
                        chain_id=self._chain_id,
                        address=addr,
                        balance=acc["balance"],
                        nonce=acc["nonce"],
                    )
                    session.add(new_acc)
                elif acc is None:
                    # Account was deleted — already removed from map, need to delete from DB
                    db_acc = session.exec(
                        select(Account).where(Account.chain_id == self._chain_id, Account.address == addr)
                    ).first()
                    if db_acc:
                        session.delete(db_acc)
                # Existing accounts were mutated in place (SQLModel tracks changes)
            session.commit()

        # Verify state root
        from .state.state_root_utils import compute_state_root_full

        with self._session_factory() as session:
            computed_hex = compute_state_root_full(session, self._chain_id)
            if computed_hex is None:
                computed_hex = "0x" + "\x00" * 32

        expected_root = diff.to_state_root
        match = computed_hex == expected_root
        if not match:
            self._logger.warning("Delta sync state root mismatch: %s != %s, rolling back", computed_hex, expected_root)
            # Rollback is implicit — we committed, but state root mismatch means we should do full sync
            return await self.sync_state_from(source_url)

        self._logger.info("Delta sync complete: %d accounts changed, state root matches", len(changed))
        return {
            "synced": len(changed),
            "created": sum(1 for c in diff.changes if c.is_new),
            "updated": sum(1 for c in diff.changes if not c.is_new and not c.is_deleted),
            "deleted": sum(1 for c in diff.changes if c.is_deleted),
            "local_state_root": computed_hex,
            "remote_state_root": expected_root,
            "match": match,
            "mode": "delta",
        }

    def import_block(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult:
        """Import a block from a remote peer.

        Handles:
        - Normal append (block extends our chain)
        - Fork resolution (block is on a longer chain)
        - Duplicate detection
        - Signature validation

        Args:
            block_data: Block data dictionary
            transactions: Optional list of transactions
            skip_state_root_validation: Skip state root validation (for bulk import)
        """
        start = time.perf_counter()
        height = block_data.get("height", -1)
        block_hash = block_data.get("hash", "")
        parent_hash = block_data.get("parent_hash", "")
        block_data.get("proposer", "")
        metrics_registry.increment("sync_blocks_received_total")
        if self._validate_signatures:
            valid, reason = self._validator.validate_block_signature(block_data)
            if not valid:
                metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning("Block rejected: signature validation failed", extra={"height": height, "reason": reason})
                return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)
        with self._session_factory() as session:
            if height == 0 and block_data.get("block_metadata"):
                is_valid, reason = self._validate_genesis_metadata(block_data, session)
                if not is_valid:
                    metrics_registry.increment("sync_state_root_rejected_total")
                    logger.error(
                        "Genesis block metadata validation failed: %s", reason, extra={"height": height, "hash": block_hash}
                    )
                    return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)
            existing = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)
            ).first()
            if existing:
                metrics_registry.increment("sync_blocks_duplicate_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash, reason="Block already exists")
            our_head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
            ).first()
            our_height = our_head.height if our_head else -1
            gap = height - our_height
            logger.info(
                "Import block check: remote height=%s, local height=%s (gap=%s), parent=%s, block=%s",
                height,
                our_height,
                gap,
                parent_hash,
                block_hash,
            )
            if height == our_height + 1:
                parent_exists = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
                ).first()
                if parent_exists or (height == 0 and parent_hash == "0x00"):
                    result = self._append_block(session, block_data, transactions, skip_state_root_validation)
                    duration = time.perf_counter() - start
                    metrics_registry.observe("sync_import_duration_seconds", duration)
                    return result
            if height <= our_height:
                existing_at_height = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)
                ).first()
                if existing_at_height and existing_at_height.hash != block_hash:
                    if our_head:
                        return self._resolve_fork(session, block_data, transactions, our_head)
                metrics_registry.increment("sync_blocks_stale_total")
                return ImportResult(
                    accepted=False, height=height, block_hash=block_hash, reason=f"Stale block (our height: {our_height})"
                )
            if height > our_height + 1:
                metrics_registry.increment("sync_blocks_gap_total")
                return ImportResult(
                    accepted=False,
                    height=height,
                    block_hash=block_hash,
                    reason=f"Gap detected (our height: {our_height}, received: {height})",
                )
        return ImportResult(accepted=False, height=height, block_hash=block_hash, reason="Unhandled import case")

    def _append_block(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult:
        """Append a block to the chain tip.

        Args:
            session: Database session
            block_data: Block data dictionary
            transactions: Optional list of transactions
            skip_state_root_validation: Skip state root validation (for bulk import)
        """
        block_hash = block_data["hash"]
        timestamp_str = block_data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(UTC)
        except (ValueError, TypeError):
            timestamp = datetime.now(UTC)
        tx_count = block_data.get("tx_count", 0)
        if transactions:
            tx_count = len(transactions)
        block = Block(
            chain_id=self._chain_id,
            height=block_data["height"],
            hash=block_data["hash"],
            parent_hash=block_data["parent_hash"],
            proposer=block_data.get("proposer", "unknown"),
            timestamp=timestamp,
            tx_count=tx_count,
            state_root=block_data.get("state_root"),
        )
        session.add(block)
        if transactions:
            # Parallel transaction validation path (v0.6.1).
            # When enabled and the conflict rate is low enough, transactions are
            # partitioned into conflict-free groups and their state deltas are
            # computed in parallel using pure functions (no DB access). Deltas are
            # applied to an in-memory account_map in tx-index order (deterministic)
            # so the resulting state root matches the sequential path exactly.
            parallel_applied = False
            if settings.parallel_tx_validation:
                # Build dependency graph from read/write sets.
                graph = DependencyGraph()
                tx_hash_to_data: dict[str, dict[str, Any]] = {}
                tx_hash_to_index: dict[str, int] = {}
                for idx, tx_data in enumerate(transactions):
                    tx_hash = tx_data.get("tx_hash", "")
                    tx_hash_to_data[tx_hash] = tx_data
                    tx_hash_to_index[tx_hash] = idx
                    read_set, write_set = extract_read_write_sets(tx_data)
                    graph.add_transaction(tx_hash, read_set, write_set, index=idx)
                groups = graph.get_conflict_groups()
                # Fall back to sequential if too many transactions conflict.
                if groups and graph.conflict_rate() <= settings.conflict_threshold:
                    # Batch-fetch all sender/recipient accounts into account_map.
                    unique_addresses: set[str] = set()
                    for tx_data in transactions:
                        sender_addr = tx_data.get("from", "")
                        recipient_addr = tx_data.get("to", "")
                        if sender_addr:
                            unique_addresses.add(sender_addr)
                        if recipient_addr:
                            unique_addresses.add(recipient_addr)
                    account_map: dict[str, Account] = {}
                    if unique_addresses:
                        existing_accounts = session.exec(
                            select(Account).where(
                                Account.chain_id == self._chain_id,
                                Account.address.in_(unique_addresses),  # type: ignore[attr-defined]
                            )
                        ).all()
                        account_map = {acc.address: acc for acc in existing_accounts}
                    # Batch-fetch tx hashes already in the DB (duplicate detection).
                    existing_tx_hashes: set[str] = set()
                    all_tx_hashes = [tx_data.get("tx_hash", "") for tx_data in transactions]
                    if all_tx_hashes:
                        existing_rows = session.exec(
                            select(ChainTransaction.tx_hash).where(
                                ChainTransaction.chain_id == self._chain_id,
                                ChainTransaction.tx_hash.in_(all_tx_hashes),  # type: ignore[attr-defined]
                            )
                        ).all()
                        existing_tx_hashes = set(existing_rows)
                    # Execute groups sequentially; within each group, deltas are
                    # computed in parallel (group members are conflict-free).
                    executor = ParallelExecutor(max_workers=settings.parallel_workers)
                    all_deltas: list[StateDelta] = []
                    try:

                        def _compute_delta(tx_data: dict[str, Any]) -> StateDelta:
                            txh = tx_data.get("tx_hash", "")
                            return compute_state_delta(account_map, tx_data, self._chain_id, txh, existing_tx_hashes)

                        for group in groups:
                            # Update nonces from account_map before processing each group
                            # (conflicting txs in later groups need updated nonces)
                            for txh in group:
                                tx_data = tx_hash_to_data[txh]
                                sender = tx_data.get("from", "")
                                sender_account = account_map.get(sender)
                                if sender_account:
                                    tx_data["nonce"] = sender_account.nonce
                                    tx_data["value"] = tx_data.get("amount", 0)
                            group_txs = [tx_hash_to_data[txh] for txh in group]
                            group_results = executor.execute_groups([group_txs], _compute_delta)[0]
                            # Apply successful deltas to account_map in tx-index
                            # order within the group (deterministic). Group members
                            # are conflict-free so application order does not affect
                            # the final state, but we keep index order for safety.
                            group_results_sorted = sorted(group_results, key=lambda d: tx_hash_to_index.get(d.tx_hash, 0))
                            for delta in group_results_sorted:
                                if delta.success:
                                    apply_delta_to_map(account_map, delta, self._chain_id)
                                    existing_tx_hashes.add(delta.tx_hash)
                            all_deltas.extend(group_results_sorted)
                    finally:
                        executor.close()
                    # Collect successful deltas in tx-index order (deterministic).
                    successful_deltas = sorted(
                        [d for d in all_deltas if d.success],
                        key=lambda d: tx_hash_to_index.get(d.tx_hash, 0),
                    )
                    # Batch-write all deltas to the DB.
                    apply_deltas_to_db(session, successful_deltas, self._chain_id)
                    # Create Transaction records for all successful txs.
                    for delta in successful_deltas:
                        tx_data = tx_hash_to_data.get(delta.tx_hash, {})
                        tx = ChainTransaction(
                            chain_id=self._chain_id,
                            tx_hash=delta.tx_hash,
                            block_height=block_data["height"],
                            sender=delta.sender,
                            recipient=delta.recipient,
                            payload=tx_data,
                            type=delta.tx_type,
                            value=tx_data.get("value", tx_data.get("amount", 0)),
                            fee=tx_data.get("fee", 0),
                            nonce=tx_data.get("nonce", 0),
                            status="confirmed",
                        )
                        session.add(tx)
                    # Log failed transactions.
                    for delta in all_deltas:
                        if not delta.success:
                            logger.warning("[SYNC] Failed to apply transaction %s: %s", delta.tx_hash, delta.error)
                    parallel_applied = True
            if not parallel_applied:
                # Sequential path (fallback when parallel_tx_validation is off
                # or the conflict rate exceeds the threshold).
                for tx_data in transactions:
                    sender_addr = tx_data.get("from", "")
                    recipient_addr = tx_data.get("to", "")
                    int(tx_data.get("amount", 0) or 0)
                    int(tx_data.get("fee", 0) or 0)
                    tx_hash = tx_data.get("tx_hash", "")
                    sender_acct = session.get(Account, (self._chain_id, sender_addr))
                    if sender_acct is None:
                        sender_acct = Account(chain_id=self._chain_id, address=sender_addr, balance=0, nonce=0)
                        session.add(sender_acct)
                        session.flush()
                    recipient_acct = session.get(Account, (self._chain_id, recipient_addr))
                    if recipient_acct is None:
                        recipient_acct = Account(chain_id=self._chain_id, address=recipient_addr, balance=0, nonce=0)
                        session.add(recipient_acct)
                        session.flush()
                    state_transition = get_state_transition()
                    success, error_msg = state_transition.apply_transaction(session, self._chain_id, tx_data, tx_hash)
                    if not success:
                        logger.warning("[SYNC] Failed to apply transaction %s: %s", tx_hash, error_msg)
                    tx_type = tx_data.get("type", "TRANSFER")
                    if tx_type:
                        tx_type = tx_type.upper()
                    else:
                        tx_type = "TRANSFER"
                    tx = ChainTransaction(
                        chain_id=self._chain_id,
                        tx_hash=tx_hash,
                        block_height=block_data["height"],
                        sender=sender_addr,
                        recipient=recipient_addr,
                        payload=tx_data,
                        type=tx_type,
                    )
                    session.add(tx)
        if block_data.get("state_root") and (not skip_state_root_validation):
            session.flush()
            # Use incremental state root computation — track changed addresses
            # during tx processing, then only re-read those accounts.
            changed_addresses: set[str] = set()
            if transactions:
                for tx_data in transactions:
                    sender_addr = tx_data.get("from", "")
                    recipient_addr = tx_data.get("to", "")
                    if sender_addr:
                        changed_addresses.add(sender_addr)
                    if recipient_addr:
                        changed_addresses.add(recipient_addr)
            # Build account_map from changed addresses (batch read)
            account_map: dict[str, Account] = {}  # type: ignore[no-redef]
            if changed_addresses:
                existing = session.exec(
                    select(Account).where(
                        Account.chain_id == self._chain_id,
                        Account.address.in_(changed_addresses),  # type: ignore[attr-defined]
                    )
                ).all()
                account_map = {acc.address: acc for acc in existing}
            from .state.state_root_utils import compute_state_root_incremental

            computed_hex = compute_state_root_incremental(session, self._chain_id, account_map, changed_addresses)
            if computed_hex is None:
                # Fallback to full recompute if incremental fails
                from .state.state_root_utils import compute_state_root_full

                computed_hex = compute_state_root_full(session, self._chain_id)
            computed_root = bytes.fromhex(computed_hex.replace("0x", "")) if computed_hex else None
            try:
                expected_root = bytes.fromhex(str(block_data.get("state_root")).replace("0x", ""))
            except ValueError:
                expected_root = None
            if expected_root is None or len(expected_root) != 32:
                metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    "[SYNC] Invalid state root at height %s: %s - BLOCK REJECTED",
                    block_data["height"],
                    block_data.get("state_root"),
                )
                self._check_and_trigger_resync(self._chain_id)
                return ImportResult(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"Invalid state root: {block_data.get('state_root')}",
                )
            elif computed_root != expected_root:
                metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    "[SYNC] State root mismatch at height %s: expected %s, computed %s - BLOCK REJECTED",
                    block_data["height"],
                    expected_root.hex(),
                    computed_root.hex(),  # type: ignore[union-attr]
                )
                self._check_and_trigger_resync(self._chain_id)
                return ImportResult(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"State root mismatch: expected {expected_root.hex()}, computed {computed_root.hex()}",  # type: ignore[union-attr]
                )
        session.commit()
        self._reset_rejection_counter(self._chain_id)
        metrics_registry.increment("sync_blocks_accepted_total")
        metrics_registry.set_gauge("sync_chain_height", float(block_data["height"]))
        logger.info(
            "Imported block",
            extra={
                "height": block_data["height"],
                "hash": block_data["hash"],
                "proposer": block_data.get("proposer"),
                "tx_count": tx_count,
            },
        )
        return ImportResult(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="Appended to chain"
        )

    def _resolve_fork(
        self, session: Session, block_data: dict[str, Any], transactions: list[dict[str, Any]] | None, our_head: Block
    ) -> ImportResult:
        """Resolve a fork using longest-chain rule.

        For PoA, we use a simple rule: if the incoming block's height is at or below
        our head and the parent chain is longer, we reorg. Otherwise, we keep our chain.
        Since we only receive one block at a time, we can only detect the fork — actual
        reorg requires the full competing chain. For now, we log the fork and reject
        unless the block has a strictly higher height.
        """
        fork_height = block_data.get("height", -1)
        our_height = our_head.height
        fork_chain_id = block_data.get("chain_id", "")
        fork_hash = block_data.get("hash", "")
        our_hash = our_head.hash if our_head else ""
        metrics_registry.increment("sync_forks_detected_total")
        logger.warning(
            "Fork detected at height %s (our height: %s, fork hash: %s..., our hash: %s...)",
            fork_height,
            our_height,
            fork_hash[:16],
            our_hash[:16],
            extra={
                "fork_height": fork_height,
                "our_height": our_height,
                "fork_hash": fork_hash,
                "our_hash": our_hash,
                "fork_chain_id": fork_chain_id,
                "our_chain_id": self._chain_id,
            },
        )
        if fork_chain_id and fork_chain_id != self._chain_id:
            return ImportResult(
                accepted=False,
                height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Incompatible chain: block from chain '{fork_chain_id}' does not match our chain '{self._chain_id}' (heights: {fork_height} vs {our_height})",
            )
        if fork_height <= our_height:
            return ImportResult(
                accepted=False,
                height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Fork rejected: our chain is longer or equal ({our_height} >= {fork_height})",
            )
        reorg_depth = our_height - fork_height + 1
        if reorg_depth > self._max_reorg_depth:
            metrics_registry.increment("sync_reorg_rejected_total")
            return ImportResult(
                accepted=False,
                height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Reorg depth {reorg_depth} exceeds max {self._max_reorg_depth}",
            )
        blocks_to_remove = session.exec(
            select(Block)
            .where(Block.chain_id == self._chain_id)
            .where(Block.height >= fork_height)
            .order_by(text("height DESC"))
        ).all()
        removed_count = 0
        for old_block in blocks_to_remove:
            old_txs = session.exec(
                select(ChainTransaction)
                .where(ChainTransaction.chain_id == self._chain_id)
                .where(ChainTransaction.block_height == old_block.height)
            ).all()
            for tx in old_txs:
                session.delete(tx)
            session.delete(old_block)
            removed_count += 1
        session.commit()
        metrics_registry.increment("sync_reorgs_total")
        metrics_registry.observe("sync_reorg_depth", float(removed_count))
        logger.warning("Chain reorg performed", extra={"removed_blocks": removed_count, "new_height": fork_height})
        result = self._append_block(session, block_data, transactions)
        result.reorged = True
        result.reorg_depth = removed_count
        return result

    def get_sync_status(self) -> dict[str, Any]:
        """Get current sync status and metrics."""
        with self._session_factory() as session:
            head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
            ).first()
            total_blocks = session.exec(select(Block).where(Block.chain_id == self._chain_id)).all()
            total_txs = session.exec(select(ChainTransaction).where(ChainTransaction.chain_id == self._chain_id)).all()
        return {
            "chain_id": self._chain_id,
            "head_height": head.height if head else -1,
            "head_hash": head.hash if head else None,
            "head_proposer": head.proposer if head else None,
            "head_timestamp": head.timestamp.isoformat() if head else None,
            "total_blocks": len(total_blocks),
            "total_transactions": len(total_txs),
            "validate_signatures": self._validate_signatures,
            "trusted_proposers": list(self._validator.trusted_proposers),
            "max_reorg_depth": self._max_reorg_depth,
        }
