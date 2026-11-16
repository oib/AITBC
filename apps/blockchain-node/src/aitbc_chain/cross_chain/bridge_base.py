"""Typed base protocol for shared bridge mixin attributes and methods."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from aitbc.bridge import ValidatorSetRegistry
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from ..models import BridgeBlockHeader, CrossChainTransfer
from .bridge_types import BridgeTransfer

# Expected failure surface for the best-effort bridge paths in the
# bridge_transfer_* mixins: SQLAlchemy driver errors, OS/asyncio transport
# errors, lazy imports, JSON/data-shape decode, crypto signing (ValueError),
# and arithmetic on untrusted amounts. Genuine BaseExceptions (incl.
# asyncio.CancelledError) still propagate (#1860).
_OPS_ERRORS = (
    ImportError,
    SQLAlchemyError,
    ArithmeticError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
)


class BridgeBase(Protocol):
    """Attributes and methods required by the bridge transfer/validator/finality mixins."""

    _session_factory: Callable[..., Any]
    _pending_transfers: dict[str, BridgeTransfer]
    _processed_proofs: set[str]

    def _session_for(self, chain_id: str = "") -> AbstractContextManager[Session]: ...

    _validator_registry: ValidatorSetRegistry
    _validator_cache_loaded: set[tuple[str, int]]
    _oracle: Any
    _merkle_verifier: Any

    # Validator set
    def get_validator_set(self, chain_id: str, epoch: int | None = None) -> Any: ...
    def _verify_threshold_signatures(self, proof: dict[str, Any], header: Any | None = None) -> bool: ...
    def _check_validator_set_freshness(self, chain_id: str, epoch: int | None = None) -> bool: ...

    # Finality / block headers
    def _get_block_header(self, chain_id: str, height: int) -> BridgeBlockHeader | None: ...
    def _update_finality(self, chain_id: str, header: BridgeBlockHeader, session: Any, commit: bool = True) -> None: ...
    def _verify_block_header_signature(self, header: BridgeBlockHeader) -> bool: ...
    def _verify_merkle_proof(self, state_root: str, proof: dict[str, Any]) -> bool: ...
    def _check_finality_for_transfer(self, header: BridgeBlockHeader, amount: int) -> bool: ...

    # BridgeTransfer* mixin cross-references — the transfer lifecycle is split
    # across bridge_transfer_{intake,confirm,proof,finalizer}; each mixin may
    # call methods owned by a sibling, so the shared surface is declared here.
    def _generate_transfer_id(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, timestamp: int
    ) -> str: ...
    def _ledger_register(self, record: CrossChainTransfer) -> None: ...
    def _sign_bridge_credit(
        self,
        credit: dict[str, Any],
        tx_hash: str,
        payload: dict[str, Any] | None = None,
        target_chain: str | None = None,
    ) -> None: ...
    def _chain_db_ready(self, chain_id: str) -> bool: ...
    def _build_transfer_from_record(
        self, record: CrossChainTransfer, proof: dict[str, Any] | None = None
    ) -> BridgeTransfer: ...
    def _validate_proof(
        self, proof: dict[str, Any], record: CrossChainTransfer, require_leaf_binding: bool = False
    ) -> bool: ...
    def build_proof(
        self, transfer_id: str, source_chain: str | None = None, block_height: int = 1, block_hash: str = ""
    ) -> dict[str, Any]: ...
    def confirm_transfer(self, transfer_id: str, proof: dict[str, Any]) -> BridgeTransfer: ...
    def list_pending_transfers(self, chain_id: str | None = None) -> list[BridgeTransfer]: ...
