"""Typed base protocol for shared bridge mixin attributes and methods."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from aitbc.bridge import ValidatorSetRegistry

from ..models import BridgeBlockHeader
from .bridge_types import BridgeTransfer


class BridgeBase(Protocol):
    """Attributes and methods required by the bridge transfer/validator/finality mixins."""

    _session_factory: Callable[[], Any]
    _pending_transfers: dict[str, BridgeTransfer]
    _processed_proofs: set[str]
    _validator_registry: ValidatorSetRegistry
    _validator_cache_loaded: set[tuple[str, int]]
    _oracle: Any
    _merkle_verifier: Any

    # Validator set
    def get_validator_set(self, chain_id: str, epoch: int | None = None) -> Any: ...
    def _verify_threshold_signatures(self, proof: dict[str, Any]) -> bool: ...
    def _check_validator_set_freshness(self, chain_id: str) -> bool: ...

    # Finality / block headers
    def _get_block_header(self, chain_id: str, height: int) -> BridgeBlockHeader | None: ...
    def _update_finality(self, chain_id: str, header: BridgeBlockHeader, session: Any, commit: bool = True) -> None: ...
    def _verify_block_header_signature(self, header: BridgeBlockHeader) -> bool: ...
    def _verify_merkle_proof(self, state_root: str, proof: dict[str, Any]) -> bool: ...
    def _check_finality_for_transfer(self, header: BridgeBlockHeader, amount: int) -> bool: ...
