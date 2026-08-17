"""Typed base protocol for shared sync mixin attributes and methods."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from sqlmodel import Session

from aitbc.sync import PeerCapabilityTracker

from .base_models import Block
from .sync_validator import ImportResult, ProposerSignatureValidator

if TYPE_CHECKING:
    # Imported for typing only: sync_divergence imports SyncBase from here at runtime.
    from .sync_divergence import Divergence


class SyncBase(Protocol):
    """Attributes and methods required by the bulk/state/import mixins."""

    # HTTP / networking
    _client: httpx.AsyncClient
    _chain_id: str
    _logger: logging.Logger

    # Database / session
    _session_factory: Callable[[], Session] | Callable[[], AbstractContextManager[Session]]

    # Sync tuning
    _poll_interval: float
    _min_bulk_sync_interval: int
    _last_bulk_sync_time: int
    _peer_tracker: PeerCapabilityTracker

    # Validation / fork handling
    _validate_signatures: bool
    _validator: ProposerSignatureValidator
    _max_reorg_depth: int
    _rejection_counts: dict[str, int]

    # Peer lifecycle
    def register_sync_peer(self, peer_id: str, rpc_url: str, block_range: tuple[int, int], has_state: bool = True) -> None: ...

    # Block import
    def import_block(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult: ...

    def _validate_genesis_metadata(self, block_data: dict[str, Any], session: Session) -> tuple[bool, str]: ...
    def _append_block(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult: ...
    def _resolve_fork(
        self, session: Session, block_data: dict[str, Any], transactions: list[dict[str, Any]] | None, our_head: Block
    ) -> ImportResult: ...

    # Divergence detection
    def detect_divergence(self, peer_url: str, peer_height: int, peer_hash: str) -> Divergence | None: ...
    async def peer_head_divergence(self, source_url: str) -> Divergence | None: ...

    # Rejection / resync
    def _track_rejection(self, chain_id: str) -> None: ...
    def _reset_rejection_counter(self, chain_id: str) -> None: ...
    def _check_and_trigger_resync(self, chain_id: str) -> bool: ...
    async def bulk_import_from(self, source_url: str) -> int: ...
