"""Bridge proof generation and validation utilities (v0.7.0 §A2).

Basic proof validation: field equality, chain_id check, block anchor
format, proposer signature format verification.

Full Merkle proof verification + proposer-set membership checking
is deferred to v0.7.2.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import BridgeProof, BridgeTransfer

logger = logging.getLogger(__name__)

REQUIRED_PROOF_FIELDS = [
    "source_chain",
    "lock_tx_hash",
    "amount",
    "sender",
    "recipient",
    "chain_id",
    "block_height",
    "block_hash",
    "proposer_signature",
]


def build_lock_proof(
    source_chain: str,
    lock_tx_hash: str,
    amount: int,
    sender: str,
    recipient: str,
    chain_id: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str,
) -> BridgeProof:
    """Build a BridgeProof from lock event fields."""
    return BridgeProof(
        source_chain=source_chain,
        lock_tx_hash=lock_tx_hash,
        amount=amount,
        sender=sender,
        recipient=recipient,
        chain_id=chain_id,
        block_height=block_height,
        block_hash=block_hash,
        proposer_signature=proposer_signature,
    )


def validate_proof_fields(proof: BridgeProof, transfer: BridgeTransfer) -> list[str]:
    """Validate proof fields against a transfer record.

    Returns a list of error messages (empty if valid).
    Does NOT verify proposer-set membership (deferred to v0.7.2).
    """
    errors: list[str] = []

    if proof.source_chain != transfer.source_chain:
        errors.append(f"source_chain mismatch: proof={proof.source_chain} vs transfer={transfer.source_chain}")
    if proof.amount != transfer.amount:
        errors.append(f"amount mismatch: proof={proof.amount} vs transfer={transfer.amount}")
    if proof.sender != transfer.sender:
        errors.append(f"sender mismatch: proof={proof.sender} vs transfer={transfer.sender}")
    if proof.recipient != transfer.recipient:
        errors.append(f"recipient mismatch: proof={proof.recipient} vs transfer={transfer.recipient}")

    # Block anchor validation
    if proof.block_height < 0:
        errors.append(f"block_height must be non-negative, got {proof.block_height}")
    if not proof.block_hash:
        errors.append("block_hash must be non-empty")

    # Signature format validation
    if not proof.proposer_signature:
        errors.append("proposer_signature must be non-empty")
    elif not proof.proposer_signature.startswith("0x"):
        errors.append("proposer_signature must be hex-encoded with 0x prefix")

    return errors


def verify_proposer_signature(proof: BridgeProof) -> str | None:
    """Verify the proposer signature and return the recovered address.

    Uses aitbc.crypto.crypto.recover_signer() for secp256k1 verification.

    Returns:
        Recovered signer address if valid, None if invalid.

    Note: This does NOT check proposer-set membership. The recovered
    address could be any valid secp256k1 signer. Full proposer-set
    verification is deferred to v0.7.2.
    """
    message_data: dict[str, Any] = {
        "source_chain": proof.source_chain,
        "lock_tx_hash": proof.lock_tx_hash,
        "amount": proof.amount,
        "sender": proof.sender,
        "recipient": proof.recipient,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
    }
    return recover_signer(message_data, proof.proposer_signature)


def proof_to_dict(proof: BridgeProof) -> dict[str, Any]:
    """Convert a BridgeProof to a dict for RPC transmission."""
    return {
        "source_chain": proof.source_chain,
        "lock_tx_hash": proof.lock_tx_hash,
        "amount": proof.amount,
        "sender": proof.sender,
        "recipient": proof.recipient,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
        "proposer_signature": proof.proposer_signature,
    }


def dict_to_proof(data: dict[str, Any]) -> BridgeProof:
    """Parse a BridgeProof from a dict (e.g., from RPC response)."""
    return BridgeProof(
        source_chain=data["source_chain"],
        lock_tx_hash=data["lock_tx_hash"],
        amount=int(data["amount"]),
        sender=data["sender"],
        recipient=data["recipient"],
        chain_id=data["chain_id"],
        block_height=int(data["block_height"]),
        block_hash=data["block_hash"],
        proposer_signature=data["proposer_signature"],
    )
