"""Chain synchronization with conflict resolution, signature validation, and metrics."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import httpx
from sqlmodel import Session

from aitbc.sync import PeerCapability, PeerCapabilityTracker

from .base_models import Account
from .config import settings
from .logger import get_logger
from .state.merkle_patricia_trie import StateManager
from .sync_block_import import BlockImportMixin
from .sync_bulk import BulkSyncMixin
from .sync_divergence import DivergenceMixin
from .sync_state import StateSyncMixin
from .sync_validator import ImportResult, ProposerSignatureValidator

__all__ = [
    "ChainSync",
    "ImportResult",
    "ProposerSignatureValidator",
    "settings",
]

logger = get_logger(__name__)


class ChainSync(BulkSyncMixin, StateSyncMixin, BlockImportMixin, DivergenceMixin):
    """Handles block import with conflict resolution for divergent chains."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | Callable[[], AbstractContextManager[Session]],
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
        self._validator = validator or ProposerSignatureValidator(
            [p.strip() for p in settings.trusted_proposers.split(",") if p.strip()]
        )
        self._validate_signatures = validate_signatures
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._client = httpx.AsyncClient(timeout=10.0, headers={"Accept-Encoding": "gzip, deflate"})
        self._last_bulk_sync_time = 0
        self._min_bulk_sync_interval = getattr(settings, "min_bulk_sync_interval", 60)
        self._rejection_counts: dict[str, int] = {}
        self._peer_tracker = PeerCapabilityTracker()

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
