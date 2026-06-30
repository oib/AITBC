"""Settlement proof chaining utilities (v0.9.0 §A4).

Provides utilities for building and verifying the settlement proof chain.
Each settlement creates a chain of proofs that anchor settlement events
to specific blocks on the source and destination chains:

.. code-block:: text

    lock (source) → verification (dest) → execution (dest) → release (dest) → settlement (source)

Each proof links to the previous one via ``previous_proof_hash``, which
is the SHA256 hash of the preceding proof. This creates a tamper-evident
chain: modifying any proof breaks the hash link to the next proof.

The proof chain enables verification that:
1. Funds were actually locked on the source chain (lock proof)
2. The destination chain verified the lock (verification proof)
3. The trade was executed on the destination chain (execution proof)
4. Funds were released on the destination chain (release proof)
5. Funds were released on the source chain (settlement proof)

For a refund (timeout) path, the chain is shorter:
    lock (source) → refund (source)  [or  lock (source) → refund (dest)]
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .types import EscrowProof, ProofType


def compute_proof_hash(proof: EscrowProof) -> str:
    """Compute the SHA256 hash of a proof for chaining.

    The hash is computed over a canonical JSON representation of the
    proof's key fields (excluding ``previous_proof_hash`` itself to
    avoid circular dependency).

    Args:
        proof: The proof to hash

    Returns:
        Hex-encoded SHA256 hash (64 characters)
    """
    data = {
        "proof_type": proof.proof_type.value,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
        "tx_hash": proof.tx_hash,
        "proposer_signature": proof.proposer_signature,
        "validator_signatures": proof.validator_signatures,
        "merkle_proof": proof.merkle_proof,
        "timestamp": proof.timestamp,
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_lock_proof(
    source_chain: str,
    lock_tx_hash: str,
    amount: int,
    sender: str,
    recipient: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str = "",
    validator_signatures: list[str] | None = None,
    merkle_proof: list[str] | None = None,
    timestamp: float = 0.0,
) -> EscrowProof:
    """Build a lock proof for the source chain.

    The lock proof is the first proof in the chain. It proves that
    funds were locked on the source chain with the correct hashlock
    and timelock parameters.

    Args:
        source_chain: Source chain ID
        lock_tx_hash: Transaction hash of the lock transaction
        amount: Amount locked
        sender: Buyer address (who locked funds)
        recipient: Seller address (who will claim)
        block_height: Block height containing the lock transaction
        block_hash: Block hash of the containing block
        proposer_signature: Signature of the block proposer
        validator_signatures: Multi-sig validator signatures (v0.7.1)
        merkle_proof: Merkle proof for the lock transaction
        timestamp: Unix timestamp of the lock

    Returns:
        EscrowProof with proof_type=LOCK and no previous_proof_hash
    """
    return EscrowProof(
        proof_type=ProofType.LOCK,
        chain_id=source_chain,
        block_height=block_height,
        block_hash=block_hash,
        tx_hash=lock_tx_hash,
        proposer_signature=proposer_signature,
        validator_signatures=validator_signatures or [],
        merkle_proof=merkle_proof or [],
        timestamp=timestamp,
        previous_proof_hash="",  # first proof in chain
    )


def build_verification_proof(
    dest_chain: str,
    verification_tx_hash: str,
    escrow_id: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str = "",
    previous_proof_hash: str = "",
    timestamp: float = 0.0,
) -> EscrowProof:
    """Build a verification proof for the destination chain.

    The verification proof proves that the destination chain verified
    the lock proof from the source chain (via bridge proof verification,
    v0.7.2 in-process verifier or external oracle).

    Args:
        dest_chain: Destination chain ID
        verification_tx_hash: Transaction hash of the verification
        escrow_id: Escrow ID being verified
        block_height: Block height containing the verification
        block_hash: Block hash of the containing block
        proposer_signature: Signature of the block proposer
        previous_proof_hash: Hash of the preceding lock proof
        timestamp: Unix timestamp of the verification

    Returns:
        EscrowProof with proof_type=VERIFICATION
    """
    return EscrowProof(
        proof_type=ProofType.VERIFICATION,
        chain_id=dest_chain,
        block_height=block_height,
        block_hash=block_hash,
        tx_hash=verification_tx_hash,
        proposer_signature=proposer_signature,
        previous_proof_hash=previous_proof_hash,
        timestamp=timestamp,
    )


def build_execution_proof(
    dest_chain: str,
    execution_tx_hash: str,
    trade_id: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str = "",
    previous_proof_hash: str = "",
    timestamp: float = 0.0,
) -> EscrowProof:
    """Build an execution proof for the destination chain.

    The execution proof proves that the trade was executed on the
    destination chain (e.g., the AI service was delivered, the compute
    job was completed).

    Args:
        dest_chain: Destination chain ID
        execution_tx_hash: Transaction hash of the execution
        trade_id: Trade ID that was executed
        block_height: Block height containing the execution
        block_hash: Block hash of the containing block
        proposer_signature: Signature of the block proposer
        previous_proof_hash: Hash of the preceding verification proof
        timestamp: Unix timestamp of the execution

    Returns:
        EscrowProof with proof_type=EXECUTION
    """
    return EscrowProof(
        proof_type=ProofType.EXECUTION,
        chain_id=dest_chain,
        block_height=block_height,
        block_hash=block_hash,
        tx_hash=execution_tx_hash,
        proposer_signature=proposer_signature,
        previous_proof_hash=previous_proof_hash,
        timestamp=timestamp,
    )


def build_release_proof(
    dest_chain: str,
    release_tx_hash: str,
    escrow_id: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str = "",
    previous_proof_hash: str = "",
    timestamp: float = 0.0,
) -> EscrowProof:
    """Build a release proof for the destination chain.

    The release proof proves that funds were released on the destination
    chain (the seller claimed funds by revealing the secret).

    Args:
        dest_chain: Destination chain ID
        release_tx_hash: Transaction hash of the release
        escrow_id: Escrow ID being released
        block_height: Block height containing the release
        block_hash: Block hash of the containing block
        proposer_signature: Signature of the block proposer
        previous_proof_hash: Hash of the preceding execution proof
        timestamp: Unix timestamp of the release

    Returns:
        EscrowProof with proof_type=RELEASE
    """
    return EscrowProof(
        proof_type=ProofType.RELEASE,
        chain_id=dest_chain,
        block_height=block_height,
        block_hash=block_hash,
        tx_hash=release_tx_hash,
        proposer_signature=proposer_signature,
        previous_proof_hash=previous_proof_hash,
        timestamp=timestamp,
    )


def build_settlement_proof(
    source_chain: str,
    settlement_tx_hash: str,
    escrow_id: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str = "",
    previous_proof_hash: str = "",
    timestamp: float = 0.0,
) -> EscrowProof:
    """Build a settlement proof for the source chain.

    The settlement proof is the final proof in the chain. It proves that
    funds were released on the source chain after verifying the release
    proof from the destination chain.

    Args:
        source_chain: Source chain ID
        settlement_tx_hash: Transaction hash of the settlement
        escrow_id: Escrow ID being settled
        block_height: Block height containing the settlement
        block_hash: Block hash of the containing block
        proposer_signature: Signature of the block proposer
        previous_proof_hash: Hash of the preceding release proof
        timestamp: Unix timestamp of the settlement

    Returns:
        EscrowProof with proof_type=SETTLEMENT
    """
    return EscrowProof(
        proof_type=ProofType.SETTLEMENT,
        chain_id=source_chain,
        block_height=block_height,
        block_hash=block_hash,
        tx_hash=settlement_tx_hash,
        proposer_signature=proposer_signature,
        previous_proof_hash=previous_proof_hash,
        timestamp=timestamp,
    )


def verify_proof_chain(proofs: list[EscrowProof]) -> list[str]:
    """Verify that a chain of proofs is valid.

    Checks:
    1. Each proof's ``previous_proof_hash`` matches the hash of the
       preceding proof (except the first proof, which must have empty
       ``previous_proof_hash``)
    2. Proof types are in the correct order:
       lock → verification → execution → release → settlement
    3. Each proof's block height is greater than the previous proof's
       block height (on the same chain) — proofs on different chains
       are not compared by height

    Args:
        proofs: Ordered list of proofs forming the chain

    Returns:
        List of error strings (empty if valid)
    """
    errors: list[str] = []

    if not proofs:
        errors.append("Proof chain is empty")
        return errors

    # Expected order of proof types in a full settlement chain
    expected_order = [
        ProofType.LOCK,
        ProofType.VERIFICATION,
        ProofType.EXECUTION,
        ProofType.RELEASE,
        ProofType.SETTLEMENT,
    ]

    # Check 1: First proof must have empty previous_proof_hash
    if proofs[0].previous_proof_hash != "":
        errors.append(
            f"First proof ({proofs[0].proof_type.value}) must have empty "
            f"previous_proof_hash, got '{proofs[0].previous_proof_hash}'"
        )

    # Check 2: Verify hash chaining
    for i in range(1, len(proofs)):
        expected_hash = compute_proof_hash(proofs[i - 1])
        if proofs[i].previous_proof_hash != expected_hash:
            errors.append(
                f"Proof {i} ({proofs[i].proof_type.value}) has "
                f"previous_proof_hash '{proofs[i].previous_proof_hash}' "
                f"but expected '{expected_hash}' (hash of proof {i - 1})"
            )

    # Check 3: Verify proof type ordering
    for i, proof in enumerate(proofs):
        if i < len(expected_order):
            if proof.proof_type != expected_order[i]:
                errors.append(f"Proof {i} has type {proof.proof_type.value} but expected {expected_order[i].value}")
        else:
            errors.append(
                f"Proof {i} has type {proof.proof_type.value} but chain should only have {len(expected_order)} proofs"
            )

    # Check 4: Block heights increase on the same chain
    chain_heights: dict[str, int] = {}
    for i, proof in enumerate(proofs):
        prev_height = chain_heights.get(proof.chain_id)
        if prev_height is not None and proof.block_height <= prev_height:
            errors.append(
                f"Proof {i} ({proof.proof_type.value}) on chain "
                f"{proof.chain_id} has block_height {proof.block_height} "
                f"but must be above previous height {prev_height}"
            )
        chain_heights[proof.chain_id] = proof.block_height

    return errors


def proof_to_dict(proof: EscrowProof) -> dict[str, Any]:
    """Convert an EscrowProof to a dict for JSON/RPC transmission."""
    return {
        "proof_type": proof.proof_type.value,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
        "tx_hash": proof.tx_hash,
        "proposer_signature": proof.proposer_signature,
        "validator_signatures": proof.validator_signatures,
        "merkle_proof": proof.merkle_proof,
        "timestamp": proof.timestamp,
        "previous_proof_hash": proof.previous_proof_hash,
    }


def dict_to_proof(data: dict[str, Any]) -> EscrowProof:
    """Parse an EscrowProof from a dict (e.g., RPC response).

    Raises:
        KeyError: If required fields are missing
        ValueError: If proof_type is not a valid ProofType
    """
    return EscrowProof(
        proof_type=ProofType(data["proof_type"]),
        chain_id=data["chain_id"],
        block_height=data["block_height"],
        block_hash=data["block_hash"],
        tx_hash=data["tx_hash"],
        proposer_signature=data.get("proposer_signature", ""),
        validator_signatures=data.get("validator_signatures", []),
        merkle_proof=data.get("merkle_proof", []),
        timestamp=data.get("timestamp", 0.0),
        previous_proof_hash=data.get("previous_proof_hash", ""),
    )
