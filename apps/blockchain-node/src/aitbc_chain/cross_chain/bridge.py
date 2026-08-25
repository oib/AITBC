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

from ..logger import get_logger
from .bridge_finality import BridgeFinalityMixin
from .bridge_transfer import BridgeTransferMixin
from .bridge_types import BridgeStatus, BridgeTransfer
from .bridge_validator import BridgeValidatorMixin

logger = get_logger(__name__)


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
    _bridge_instance = CrossChainBridge(session_factory)
    return _bridge_instance


def get_cross_chain_bridge() -> CrossChainBridge | None:
    """Get the global bridge instance."""
    return _bridge_instance


__all__ = [
    "BridgeStatus",
    "BridgeTransfer",
    "CrossChainBridge",
    "get_cross_chain_bridge",
    "init_cross_chain_bridge",
]
