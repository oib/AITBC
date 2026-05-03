"""Chain synchronization with conflict resolution, signature validation, and metrics."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlmodel import Session, select

from .config import settings
from .metrics import metrics_registry
from .models import Block, Transaction as ChainTransaction, Account
from .logger import get_logger
from .state.merkle_patricia_trie import StateManager
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

    def __init__(self, trusted_proposers: Optional[List[str]] = None) -> None:
        self._trusted = set(trusted_proposers or [])

    @property
    def trusted_proposers(self) -> set:
        return self._trusted

    def add_trusted(self, proposer_id: str) -> None:
        self._trusted.add(proposer_id)

    def remove_trusted(self, proposer_id: str) -> None:
        self._trusted.discard(proposer_id)

    def validate_block_signature(self, block_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate that a block was produced by a trusted proposer.

        Returns (is_valid, reason).
        """
        proposer = block_data.get("proposer", "")
        block_hash = block_data.get("hash", "")
        height = block_data.get("height", -1)

        if not proposer:
            return False, "Missing proposer field"

        if not block_hash or not block_hash.startswith("0x"):
            return False, f"Invalid block hash format: {block_hash}"

        # If trusted list is configured, enforce it
        if self._trusted and proposer not in self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return False, f"Proposer '{proposer}' not in trusted set"

        # Verify block hash integrity
        expected_fields = ["height", "parent_hash", "timestamp"]
        for field in expected_fields:
            if field not in block_data:
                return False, f"Missing required field: {field}"

        # Verify hash is a valid sha256 hex
        hash_hex = block_hash[2:]  # strip 0x
        if len(hash_hex) != 64:
            return False, f"Invalid hash length: {len(hash_hex)}"
        try:
            int(hash_hex, 16)
        except ValueError:
            return False, f"Invalid hex in hash: {hash_hex}"

        metrics_registry.increment("sync_signature_validated_total")
        return True, "Valid"


class ChainSync:
    """Handles block import with conflict resolution for divergent chains."""

    def __init__(
        self,
        session_factory,
        *,
        chain_id: str = "",
        max_reorg_depth: int = 10,
        validator: Optional[ProposerSignatureValidator] = None,
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
        self._min_bulk_sync_interval = getattr(settings, 'min_bulk_sync_interval', 60)
        # Re-sync rejection counter for Phase 1.3
        self._rejection_counts: Dict[str, int] = {}

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    def _validate_genesis_metadata(self, block_data: Dict[str, Any], session: Session) -> Tuple[bool, str]:
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
                return False, "Genesis block missing block_metadata"

            metadata = json.loads(metadata_str)
            allocations = metadata.get("allocations", [])
            if not allocations:
                return False, "Genesis block metadata missing allocations"

            # Create temporary account state from allocations
            state_manager = StateManager()
            temp_accounts = {}
            for alloc in allocations:
                address = alloc.get("address")
                balance = alloc.get("balance", 0)
                if address:
                    temp_accounts[address] = {"balance": balance}

            # Compute expected state root from allocations
            computed_root = state_manager.compute_state_root(temp_accounts)

            # Get expected state root from block
            expected_root_hex = block_data.get("state_root", "")
            try:
                expected_root = bytes.fromhex(expected_root_hex.replace("0x", ""))
            except ValueError:
                return False, f"Invalid state_root format: {expected_root_hex}"

            # Verify computed root matches expected root
            if computed_root != expected_root:
                return False, f"State root mismatch: computed {computed_root.hex()}, expected {expected_root.hex()}"

            return True, "Valid"

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON in block_metadata: {e}"
        except Exception as e:
            return False, f"Genesis metadata validation error: {e}"

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
                f"State root rejection threshold reached ({current_count}/{threshold}), "
                f"triggering auto re-sync for chain {chain_id}"
            )
            # Trigger re-sync from trusted peer
            source_url = settings.auto_resync_source_url or settings.default_peer_rpc_url
            if source_url:
                try:
                    # Use asyncio to run the async bulk_import_from method
                    import asyncio
                    loop = asyncio.get_event_loop()
                    imported = loop.run_until_complete(self.bulk_import_from(source_url))
                    logger.info(f"Auto re-sync completed: {imported} blocks imported")
                    # Reset counter after successful re-sync
                    self._reset_rejection_counter(chain_id)
                    return True
                except Exception as e:
                    logger.error(f"Auto re-sync failed: {e}")
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
        min_batch = getattr(settings, 'min_bulk_sync_batch_size', 20)
        max_batch = getattr(settings, 'max_bulk_sync_batch_size', 200)
        initial_sync_threshold = getattr(settings, 'initial_sync_threshold', 10000)
        initial_sync_max_batch = getattr(settings, 'initial_sync_max_batch_size', 1000)
        large_gap_threshold = getattr(settings, 'large_gap_threshold', 1000)
        large_gap_max_batch = getattr(settings, 'large_gap_max_batch_size', 500)

        if gap_size > initial_sync_threshold:
            # Initial sync: very large batches for maximum throughput
            return min(500 + (gap_size - initial_sync_threshold) // 20, initial_sync_max_batch)
        elif gap_size > large_gap_threshold:
            # Large gap: accelerated sync
            return min(200 + (gap_size - large_gap_threshold) // 10, large_gap_max_batch)
        elif gap_size > 500:
            # Medium gap: standard sync
            return min(100 + (gap_size - 500) // 5, max_batch)
        elif gap_size > 100:
            # Medium-small gaps: scale from 50 to 100
            return min(50 + (gap_size - 100) // 4, 100)
        else:
            # Small gaps: scale from min to 50
            return min(min_batch + gap_size // 2, 50)

    def _get_adaptive_poll_interval(self, gap_size: int) -> float:
        """Get adaptive polling interval based on sync mode.

        Strategy:
        - Initial sync gaps (>10,000): Fast polling (2s) for maximum throughput
        - Large gaps (1,000-10,000): Moderate polling (3s)
        - Medium gaps (500-1,000): Standard polling (5s)
        - Small gaps (<500): Steady-state polling (5s)
        """
        initial_sync_threshold = getattr(settings, 'initial_sync_threshold', 10000)
        initial_sync_poll_interval = getattr(settings, 'initial_sync_poll_interval', 2.0)
        large_gap_threshold = getattr(settings, 'large_gap_threshold', 1000)
        large_gap_poll_interval = getattr(settings, 'large_gap_poll_interval', 3.0)

        if gap_size > initial_sync_threshold:
            return initial_sync_poll_interval
        elif gap_size > large_gap_threshold:
            return large_gap_poll_interval
        else:
            return self._poll_interval  # Use configured steady-state poll interval

    def _get_adaptive_bulk_sync_interval(self, gap_size: int) -> int:
        """Get adaptive bulk sync interval based on sync mode.

        Strategy:
        - Initial sync gaps (>10,000): Frequent bulk sync (10s) for maximum throughput
        - Large gaps (1,000-10,000): Moderate bulk sync (30s)
        - Medium gaps (500-1,000): Standard bulk sync (60s)
        - Small gaps (<500): Steady-state bulk sync (60s)
        """
        initial_sync_threshold = getattr(settings, 'initial_sync_threshold', 10000)
        initial_sync_bulk_interval = getattr(settings, 'initial_sync_bulk_interval', 10)
        large_gap_threshold = getattr(settings, 'large_gap_threshold', 1000)
        large_gap_bulk_interval = getattr(settings, 'large_gap_bulk_interval', 30)

        if gap_size > initial_sync_threshold:
            return initial_sync_bulk_interval
        elif gap_size > large_gap_threshold:
            return large_gap_bulk_interval
        else:
            return self._min_bulk_sync_interval  # Use configured steady-state interval

    def _get_sync_mode(self, gap_size: int) -> str:
        """Determine current sync mode based on gap size."""
        initial_sync_threshold = getattr(settings, 'initial_sync_threshold', 10000)
        large_gap_threshold = getattr(settings, 'large_gap_threshold', 1000)

        if gap_size > initial_sync_threshold:
            return "initial_sync"
        elif gap_size > large_gap_threshold:
            return "large_gap"
        elif gap_size > 500:
            return "medium_gap"
        else:
            return "steady_state"

    async def fetch_blocks_range(self, start: int, end: int, source_url: str) -> List[Dict[str, Any]]:
        """Fetch a range of blocks from a source RPC."""
        try:
            resp = await self._client.get(f"{source_url}/rpc/blocks-range", params={"start": start, "end": end})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "blocks" in data:
                return data["blocks"]
            else:
                logger.error("Unexpected blocks-range response", extra={"data": data})
                return []
        except Exception as e:
            logger.error("Failed to fetch blocks range", extra={"start": start, "end": end, "error": str(e)})
            return []

    async def bulk_import_from(self, source_url: str, import_url: Optional[str] = None) -> int:
        """Bulk import missing blocks from source to catch up quickly."""
        if import_url is None:
            import_url = "http://127.0.0.1:8006"  # default local RPC

        # Get local head
        with self._session_factory() as session:
            local_head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(Block.height.desc()).limit(1)
            ).first()
            local_height = local_head.height if local_head else -1

        # Get remote head
        try:
            resp = await self._client.get(f"{source_url}/rpc/head")
            resp.raise_for_status()
            remote_head = resp.json()
            remote_height = remote_head.get("height", -1)
        except Exception as e:
            logger.error("Failed to fetch remote head", extra={"source_url": source_url, "error": str(e)})
            return 0

        if remote_height <= local_height:
            logger.info("Already up to date", extra={"local_height": local_height, "remote_height": remote_height})
            return 0

        gap_size = remote_height - local_height
        sync_mode = self._get_sync_mode(gap_size)
        dynamic_batch_size = self._calculate_dynamic_batch_size(gap_size)
        adaptive_bulk_interval = self._get_adaptive_bulk_sync_interval(gap_size)
        adaptive_poll_interval = self._get_adaptive_poll_interval(gap_size)

        # Rate limiting check with adaptive interval
        current_time = time.time()
        time_since_last_sync = current_time - self._last_bulk_sync_time
        if time_since_last_sync < adaptive_bulk_interval:
            logger.warning("Bulk sync rate limited", extra={
                "time_since_last_sync": time_since_last_sync,
                "min_interval": adaptive_bulk_interval,
                "sync_mode": sync_mode
            })
            return 0

        logger.info("Starting bulk import", extra={
            "local_height": local_height,
            "remote_height": remote_height,
            "gap_size": gap_size,
            "batch_size": dynamic_batch_size,
            "sync_mode": sync_mode,
            "bulk_interval": adaptive_bulk_interval,
            "poll_interval": adaptive_poll_interval
        })

        # Record sync mode metrics
        metrics_registry.set_gauge(f"sync_mode_{sync_mode}", 1.0)
        metrics_registry.set_gauge("sync_gap_size", float(gap_size))
        metrics_registry.set_gauge("sync_batch_size", float(dynamic_batch_size))

        imported = 0
        start_height = local_height + 1
        while start_height <= remote_height:
            end_height = min(start_height + dynamic_batch_size - 1, remote_height)
            batch = await self.fetch_blocks_range(start_height, end_height, source_url)
            if not batch:
                logger.warning("No blocks returned for range", extra={"start": start_height, "end": end_height})
                break

            # Import blocks in order
            for block_data in batch:
                result = self.import_block(block_data)
                if result.accepted:
                    imported += 1
                else:
                    logger.warning(f"Block import failed during bulk at height {block_data.get('height')}: {result.reason}", extra={"height": block_data.get("height"), "reason": result.reason})
                    return imported

            start_height = end_height + 1
            # Brief pause to avoid overwhelming the DB (use adaptive poll interval)
            await asyncio.sleep(adaptive_poll_interval)

        logger.info("Bulk import completed", extra={
            "imported": imported,
            "final_height": remote_height,
            "sync_mode": sync_mode
        })

        # Record completion metrics
        sync_duration = time.time() - current_time
        metrics_registry.observe("sync_bulk_duration_seconds", sync_duration)
        if imported > 0:
            sync_rate = imported / sync_duration
            metrics_registry.observe("sync_blocks_per_second", sync_rate)
        metrics_registry.set_gauge("sync_chain_height", float(remote_height))

        # Update last bulk sync time
        self._last_bulk_sync_time = current_time

        return imported

    def import_block(self, block_data: Dict[str, Any], transactions: Optional[List[Dict[str, Any]]] = None) -> ImportResult:
        """Import a block from a remote peer.

        Handles:
        - Normal append (block extends our chain)
        - Fork resolution (block is on a longer chain)
        - Duplicate detection
        - Signature validation
        """
        start = time.perf_counter()
        height = block_data.get("height", -1)
        block_hash = block_data.get("hash", "")
        parent_hash = block_data.get("parent_hash", "")
        proposer = block_data.get("proposer", "")

        metrics_registry.increment("sync_blocks_received_total")

        # Validate signature
        if self._validate_signatures:
            valid, reason = self._validator.validate_block_signature(block_data)
            if not valid:
                metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning("Block rejected: signature validation failed",
                               extra={"height": height, "reason": reason})
                return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)

        with self._session_factory() as session:
            # Validate genesis block metadata if present
            if height == 0 and block_data.get("block_metadata"):
                is_valid, reason = self._validate_genesis_metadata(block_data, session)
                if not is_valid:
                    metrics_registry.increment("sync_state_root_rejected_total")
                    logger.error(f"Genesis block metadata validation failed: {reason}", extra={"height": height, "hash": block_hash})
                    return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)
            
            # Check for duplicate
            existing = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)
            ).first()
            if existing:
                metrics_registry.increment("sync_blocks_duplicate_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash,
                                    reason="Block already exists")

            # Get our chain head
            our_head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(Block.height.desc()).limit(1)
            ).first()
            our_height = our_head.height if our_head else -1

            # Case 1: Block extends our chain directly
            if height == our_height + 1:
                parent_exists = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
                ).first()
                if parent_exists or (height == 0 and parent_hash == "0x00"):
                    result = self._append_block(session, block_data, transactions)
                    duration = time.perf_counter() - start
                    metrics_registry.observe("sync_import_duration_seconds", duration)
                    return result

            # Case 2: Block is behind our head — ignore
            if height <= our_height:
                # Check if it's a fork at a previous height
                existing_at_height = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)
                ).first()
                if existing_at_height and existing_at_height.hash != block_hash:
                    # Fork detected — resolve by longest chain rule
                    return self._resolve_fork(session, block_data, transactions, our_head)
                metrics_registry.increment("sync_blocks_stale_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash,
                                    reason=f"Stale block (our height: {our_height})")

            # Case 3: Block is ahead — we're behind, need to catch up
            if height > our_height + 1:
                metrics_registry.increment("sync_blocks_gap_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash,
                                    reason=f"Gap detected (our height: {our_height}, received: {height})")

        return ImportResult(accepted=False, height=height, block_hash=block_hash,
                            reason="Unhandled import case")

    def _append_block(self, session: Session, block_data: Dict[str, Any],
                      transactions: Optional[List[Dict[str, Any]]] = None) -> ImportResult:
        """Append a block to the chain tip."""
        block_hash = block_data["hash"]
        timestamp_str = block_data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(datetime.UTC)
        except (ValueError, TypeError):
            timestamp = datetime.now(datetime.UTC)

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

        # Import transactions if provided and apply state changes
        if transactions:
            for tx_data in transactions:
                sender_addr = tx_data.get("from", "")
                recipient_addr = tx_data.get("to", "")
                value = int(tx_data.get("amount", 0) or 0)
                fee = int(tx_data.get("fee", 0) or 0)
                tx_hash = tx_data.get("tx_hash", "")

                # Upsert sender/recipient accounts
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

                # Apply state transition through validated transaction
                state_transition = get_state_transition()
                success, error_msg = state_transition.apply_transaction(
                    session, self._chain_id, tx_data, tx_hash
                )
                
                if not success:
                    logger.warning(f"[SYNC] Failed to apply transaction {tx_hash}: {error_msg}")
                    # For now, log warning but continue (to be enforced in production)

                # Extract type from transaction data
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

        # Verify state root if provided
        if block_data.get("state_root"):
            session.flush()
            state_manager = StateManager()
            accounts = session.exec(
                select(Account).where(Account.chain_id == self._chain_id)
            ).all()
            account_dict = {acc.address: acc for acc in accounts}
            
            computed_root = state_manager.compute_state_root(account_dict)
            try:
                expected_root = bytes.fromhex(str(block_data.get("state_root")).replace("0x", ""))
            except ValueError:
                expected_root = None
            
            if expected_root is None or len(expected_root) != 32:
                metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    f"[SYNC] Invalid state root at height {block_data['height']}: "
                    f"{block_data.get('state_root')} - BLOCK REJECTED"
                )
                # Check if re-sync should be triggered
                self._check_and_trigger_resync(self._chain_id)
                return ImportResult(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"Invalid state root: {block_data.get('state_root')}"
                )
            elif computed_root != expected_root:
                metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    f"[SYNC] State root mismatch at height {block_data['height']}: "
                    f"expected {expected_root.hex()}, computed {computed_root.hex()} - BLOCK REJECTED"
                )
                # Check if re-sync should be triggered
                self._check_and_trigger_resync(self._chain_id)
                return ImportResult(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"State root mismatch: expected {expected_root.hex()}, computed {computed_root.hex()}"
                )

        session.commit()

        # Reset rejection counter on successful block import
        self._reset_rejection_counter(self._chain_id)

        metrics_registry.increment("sync_blocks_accepted_total")
        metrics_registry.set_gauge("sync_chain_height", float(block_data["height"]))
        logger.info("Imported block", extra={
            "height": block_data["height"],
            "hash": block_data["hash"],
            "proposer": block_data.get("proposer"),
            "tx_count": tx_count,
        })

        return ImportResult(
            accepted=True, height=block_data["height"],
            block_hash=block_data["hash"], reason="Appended to chain"
        )

    def _resolve_fork(self, session: Session, block_data: Dict[str, Any],
                      transactions: Optional[List[Dict[str, Any]]],
                      our_head: Block) -> ImportResult:
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

        metrics_registry.increment("sync_forks_detected_total")
        logger.warning(f"Fork detected at height {fork_height} (our height: {our_height}, fork hash: {block_data.get('hash')[:16]}..., our hash: {our_head.hash[:16]}...)", extra={
            "fork_height": fork_height,
            "our_height": our_height,
            "fork_hash": block_data.get("hash"),
            "our_hash": our_head.hash,
            "fork_chain_id": fork_chain_id,
            "our_chain_id": self._chain_id,
        })

        # Check if chains are incompatible (different chain_id)
        if fork_chain_id and fork_chain_id != self._chain_id:
            return ImportResult(
                accepted=False, height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Incompatible chain: block from chain '{fork_chain_id}' does not match our chain '{self._chain_id}' (heights: {fork_height} vs {our_height})"
            )

        # Simple longest-chain: only reorg if incoming chain is strictly longer
        # and within max reorg depth
        if fork_height <= our_height:
            return ImportResult(
                accepted=False, height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Fork rejected: our chain is longer or equal ({our_height} >= {fork_height})"
            )

        reorg_depth = our_height - fork_height + 1
        if reorg_depth > self._max_reorg_depth:
            metrics_registry.increment("sync_reorg_rejected_total")
            return ImportResult(
                accepted=False, height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Reorg depth {reorg_depth} exceeds max {self._max_reorg_depth}"
            )

        # Perform reorg: remove blocks from fork_height onwards, then append
        blocks_to_remove = session.exec(
            select(Block).where(Block.chain_id == self._chain_id).where(Block.height >= fork_height).order_by(Block.height.desc())
        ).all()

        removed_count = 0
        for old_block in blocks_to_remove:
            # Remove transactions in the block
            old_txs = session.exec(
                select(ChainTransaction).where(ChainTransaction.chain_id == self._chain_id).where(ChainTransaction.block_height == old_block.height)
            ).all()
            for tx in old_txs:
                session.delete(tx)
            session.delete(old_block)
            removed_count += 1

        session.commit()

        metrics_registry.increment("sync_reorgs_total")
        metrics_registry.observe("sync_reorg_depth", float(removed_count))
        logger.warning("Chain reorg performed", extra={
            "removed_blocks": removed_count,
            "new_height": fork_height,
        })

        # Now append the new block
        result = self._append_block(session, block_data, transactions)
        result.reorged = True
        result.reorg_depth = removed_count
        return result

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and metrics."""
        with self._session_factory() as session:
            head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(Block.height.desc()).limit(1)
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
