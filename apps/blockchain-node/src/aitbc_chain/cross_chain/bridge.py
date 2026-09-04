"""
Cross-Chain Bridge - Real cross-island transaction bridging.

This module implements atomic cross-chain transfers using a
lock-mint/burn-release pattern for secure value transfer
between islands (blockchain shards).
"""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from typing import Any
from collections.abc import Iterator

from aitbc.bridge import ValidatorSetRegistry
from sqlmodel import Session

from ..config import settings
from ..logger import get_logger
from .bridge_finality import BridgeFinalityMixin
from .bridge_transfer import BridgeTransferMixin
from .bridge_types import BridgeStatus, BridgeTransfer
from .bridge_validator import BridgeValidatorMixin

logger = get_logger(__name__)


class BridgeProductionSafetyError(RuntimeError):
    """Raised when the bridge release path is enabled without required safety controls."""

    pass


def _validate_bridge_production_safety() -> None:
    """Fail-closed guard for the cross-chain bridge release path.

    When ``settings.bridge_release_enabled`` is True, the bridge is only allowed to start
    if the production security controls are explicitly configured:

    - multi-sig is enabled (``bridge_multisig_enabled``)
    - Merkle proof verification is enforced (``bridge_require_merkle_proof``)
    - block header signatures are required (``bridge_block_signature_required``)
    - validator administration is configured (``bridge_admin_addresses``)
    - at least one supported chain is configured (``bridge_supported_chains``)
    - the multi-sig threshold is sane (1 < threshold <= validators)

    This guard runs during ``init_cross_chain_bridge`` so an unsafe production
    configuration refuses node startup instead of silently enabling value-moving
    bridge operations.
    """
    if not getattr(settings, "bridge_release_enabled", False):
        return

    def _fail(message: str) -> None:
        logger.error("Bridge production safety: %s", message)
        raise BridgeProductionSafetyError(message)

    if not getattr(settings, "bridge_multisig_enabled", False):
        _fail("bridge_release_enabled=True requires bridge_multisig_enabled=True")

    if not getattr(settings, "bridge_require_merkle_proof", False):
        _fail("bridge_release_enabled=True requires bridge_require_merkle_proof=True")

    if not getattr(settings, "bridge_block_signature_required", False):
        _fail("bridge_release_enabled=True requires bridge_block_signature_required=True")

    admin_addresses = getattr(settings, "bridge_admin_addresses", "")
    if not admin_addresses or not admin_addresses.strip():
        _fail("bridge_release_enabled=True requires bridge_admin_addresses to be configured")

    supported_chains = getattr(settings, "bridge_supported_chains", "")
    if not supported_chains or not supported_chains.strip():
        _fail("bridge_release_enabled=True requires bridge_supported_chains to be configured")

    threshold = int(getattr(settings, "bridge_multisig_threshold", 0))
    validators = int(getattr(settings, "bridge_multisig_validators", 0))
    if threshold <= 1:
        _fail("bridge_multisig_threshold must be > 1 when bridge_release_enabled=True")
    if validators < threshold:
        _fail(f"bridge_multisig_validators ({validators}) must be >= threshold ({threshold})")

    verification_mode = getattr(settings, "bridge_verification_mode", "in_process")
    if verification_mode not in {"in_process", "oracle"}:
        _fail("bridge_verification_mode must be 'in_process' or 'oracle'")

    if verification_mode == "oracle":
        endpoints = getattr(settings, "bridge_oracle_endpoints", [])
        if not endpoints:
            _fail("bridge_verification_mode='oracle' requires bridge_oracle_endpoints")


class CrossChainBridge(BridgeTransferMixin, BridgeValidatorMixin, BridgeFinalityMixin):
    """
    Cross-Chain Bridge for atomic transfers between islands.

    Implements the lock-mint/burn-release pattern:
    1. Lock funds on source chain
    2. Generate proof of lock
    3. Mint/burn equivalent on target chain
    4. Release funds on target
    """

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._pending_transfers: dict[str, BridgeTransfer] = {}
        self._processed_proofs: set[str] = set()
        # v0.7.1: Validator set registry for multi-sig threshold verification.
        # Loaded from the BridgeValidator table on demand and cached in-memory.
        self._validator_registry: ValidatorSetRegistry = ValidatorSetRegistry()
        self._validator_cache_loaded: set[tuple[str, int]] = set()  # (chain_id, epoch) loaded
        # v0.7.2: In-process verifier for Merkle proof + finality verification.
        # Initialized lazily on first use to avoid import-time dependency on
        # the Merkle Patricia Trie.
        self._oracle: Any = None
        self._merkle_verifier: Any = None
        # v0.7.3: Bridge is multi-chain aware. Decide at init whether the
        # supplied session factory accepts a chain_id argument.
        self._session_factory_accepts_chain_id = self._factory_accepts_chain_id(session_factory)

    @staticmethod
    def _factory_accepts_chain_id(session_factory: Any) -> bool:
        """Return True if session_factory can be called with a chain_id."""
        try:
            sig = inspect.signature(session_factory)
            params = list(sig.parameters.values())
            if not params:
                return False
            # A single positional/keyword parameter is treated as chain_id.
            return len(params) == 1 and params[0].kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_ONLY,
            )
        except (TypeError, ValueError):
            return False

    @contextmanager
    def _session_for(self, chain_id: str = "") -> Iterator[Session]:
        """Open a session for the requested chain, if the factory supports it.

        Falls back to the legacy no-argument factory for unit tests that use
        a single in-memory engine.
        """
        if chain_id and self._session_factory_accepts_chain_id:
            with self._session_factory(chain_id) as session:
                yield session
        else:
            with self._session_factory() as session:
                yield session


_bridge_instance: CrossChainBridge | None = None


def init_cross_chain_bridge(session_factory: Any) -> CrossChainBridge:
    """Initialize the global cross-chain bridge."""
    global _bridge_instance
    _validate_bridge_production_safety()
    _bridge_instance = CrossChainBridge(session_factory)
    return _bridge_instance


def get_cross_chain_bridge() -> CrossChainBridge | None:
    """Get the global bridge instance."""
    return _bridge_instance


__all__ = [
    "BridgeProductionSafetyError",
    "BridgeStatus",
    "BridgeTransfer",
    "CrossChainBridge",
    "get_cross_chain_bridge",
    "init_cross_chain_bridge",
]
