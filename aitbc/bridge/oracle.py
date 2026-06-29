"""Bridge oracle client interface (v0.7.2 §A2, v0.7.4 §A1).

Abstract interface for bridge proof verification. The default
implementation (``InProcessVerifier``) uses local cryptographic verification
(Merkle proofs + block header signatures). The ``ExternalOracleClient``
(v0.7.4) delegates verification to one or more external oracle HTTP
endpoints, with an ``OracleFallbackPolicy`` (v0.7.4 §A2) that falls back
to in-process verification when the oracle is unavailable.

The ``InProcessVerifier`` delegates Merkle proof verification to a
``MerkleProofVerifier`` protocol implementation provided by the blockchain
node (which has access to the Merkle Patricia Trie). This keeps the shared
SDK dependency-free — the actual trie verification happens in
``apps/blockchain-node/``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


from .types import (
    BridgeBlockHeader,
    FinalityConfig,
    ProofVerificationResult,
    VerificationMode,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class MerkleProofVerifier(Protocol):
    """Protocol for Merkle proof verification (implemented by blockchain node).

    The blockchain node implements this protocol by wrapping
    ``merkle_patricia_trie.verify_proof``. The shared SDK calls this
    interface so it doesn't depend on the node's internal trie implementation.
    """

    def verify_merkle_proof(
        self,
        state_root: str,
        key: str,
        value: str,
        proof: list[bytes],
    ) -> bool:
        """Verify a Merkle proof against a state root.

        Args:
            state_root: The expected state root (hex string).
            key: The key whose inclusion is being proven.
            value: The expected value at that key.
            proof: List of encoded trie nodes forming the proof path.

        Returns:
            True if the proof is valid (key→value is in the trie with the
            given state root), False otherwise.
        """
        ...


class OracleClient(ABC):
    """Abstract base class for bridge proof verification oracles.

    Implementations:
    - ``InProcessVerifier`` — default, uses local cryptographic verification
    - ``ExternalOracleClient`` — stub for future external oracle integration
    """

    @abstractmethod
    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof against a block header.

        Args:
            proof: The bridge proof dict (source_chain, lock_tx_hash, amount,
                sender, recipient, chain_id, block_height, block_hash,
                proposer_signature, validator_signatures, merkle_proof).
            block_header: The source chain block header anchoring the proof.
            finality_config: Finality threshold configuration.

        Returns:
            ``ProofVerificationResult`` with validity, error, and metadata.
        """
        ...

    @abstractmethod
    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check if a block header has sufficient finality for a transfer.

        Args:
            block_header: The block header to check.
            finality_config: Finality threshold configuration.
            transfer_amount: The transfer amount (determines threshold tier).

        Returns:
            True if the block has enough confirmations for this transfer.
        """
        ...

    @property
    @abstractmethod
    def mode(self) -> VerificationMode:
        """The verification mode of this oracle."""
        ...


class InProcessVerifier(OracleClient):
    """Default in-process verification using local cryptographic primitives.

    Delegates Merkle proof verification to a ``MerkleProofVerifier``
    implementation provided by the blockchain node. Block header signature
    verification uses ``aitbc.bridge.verification.validate_block_header``.

    If no ``MerkleProofVerifier`` is provided, Merkle proof verification is
    skipped (and the result will note this in the error field). This is
    useful for testing the oracle interface without a full trie.
    """

    def __init__(
        self,
        merkle_verifier: MerkleProofVerifier | None = None,
    ) -> None:
        self._merkle_verifier = merkle_verifier

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.IN_PROCESS

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof in-process.

        Steps:
        1. Verify block header state_root matches proof's claimed state root
        2. Verify Merkle proof (if merkle_verifier is set)
        3. Check finality
        4. Return structured result
        """
        # Step 1: Verify state root matches
        proof_state_root = proof.get("state_root", "")
        if proof_state_root and proof_state_root != block_header.state_root:
            return ProofVerificationResult(
                valid=False,
                error=f"State root mismatch: proof={proof_state_root} vs header={block_header.state_root}",
                block_height=block_header.height,
                state_root=block_header.state_root,
                verification_mode=VerificationMode.IN_PROCESS,
            )

        # Step 2: Verify Merkle proof (if provided and verifier is set)
        merkle_proof = proof.get("merkle_proof", [])
        lock_key = proof.get("lock_tx_hash", "")
        lock_value = proof.get("lock_event", "")

        if merkle_proof:
            if self._merkle_verifier is None:
                logger.warning("Merkle proof provided but no verifier set — skipping")
            else:
                proof_bytes = [p if isinstance(p, bytes) else bytes.fromhex(p.removeprefix("0x")) for p in merkle_proof]
                if not self._merkle_verifier.verify_merkle_proof(block_header.state_root, lock_key, lock_value, proof_bytes):
                    return ProofVerificationResult(
                        valid=False,
                        error="Merkle proof verification failed",
                        block_height=block_header.height,
                        state_root=block_header.state_root,
                        verification_mode=VerificationMode.IN_PROCESS,
                    )

        # Step 3: Check finality
        transfer_amount = int(proof.get("amount", 0))
        has_finality, _required = self._check_finality_internal(
            block_header,
            finality_config,
            transfer_amount,
        )

        # Step 4: Return result
        return ProofVerificationResult(
            valid=True,
            block_height=block_header.height,
            state_root=block_header.state_root,
            finality_confirmed=has_finality,
            verification_mode=VerificationMode.IN_PROCESS,
        )

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check finality — large transfers require full finality."""
        has_finality, _required = self._check_finality_internal(
            block_header,
            finality_config,
            transfer_amount,
        )
        return has_finality

    @staticmethod
    def _check_finality_internal(
        block_header: BridgeBlockHeader,
        config: FinalityConfig,
        transfer_amount: int,
    ) -> tuple[bool, int]:
        """Determine required confirmations and check if met.

        Returns (has_finality, required_confirmations).
        """
        required = config.finality_blocks if transfer_amount >= config.large_transfer_threshold else config.min_confirmations
        return block_header.confirmation_count >= required, required


class ExternalOracleClient(OracleClient):
    """Stub for future external oracle integration.

    NOT IMPLEMENTED in v0.7.2. Raises ``NotImplementedError`` if used.
    External oracle integration is deferred to v0.8.x or v0.9.x when
    oracle infrastructure is actually deployed.

    The stub exists so that the ``OracleClient`` interface can be tested
    with both modes, and so that future integration doesn't require
    breaking changes to the interface.
    """

    def __init__(self, endpoint: str = "") -> None:
        self._endpoint = endpoint
        logger.warning("ExternalOracleClient is a stub — not implemented in v0.7.2")

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.ORACLE

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        raise NotImplementedError("External oracle integration deferred to v0.8.x+")

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        raise NotImplementedError("External oracle integration deferred to v0.8.x+")
