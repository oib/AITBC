"""Bridge verification utilities (v0.7.2 §A3).

Block header signature validation and finality threshold checking.
These utilities are used by the ``InProcessVerifier`` (A2) and by the
blockchain node's bridge proof verification path (B3-B4).

Block header verification uses ``aitbc.crypto.crypto.recover_signer`` to
recover the proposer's address from the block header signature. The
signed message is the canonical-JSON encoding of the block header fields
excluding the signature itself — matching the format used by PoA's
``_sign_block_hash`` in the blockchain node.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import BridgeBlockHeader, FinalityConfig, ValidatorSet

logger = logging.getLogger(__name__)


def build_verification_message(header: BridgeBlockHeader) -> dict[str, Any]:
    """Build the canonical message dict that a block header proposer signs.

    This is the block header without the ``signature``,
    ``finality_confirmed``, ``confirmation_count``, and ``timestamp``
    fields. Key ordering does not matter — ``recover_signer`` re-serializes
    with ``sort_keys=True`` before hashing.

    The fields included in the signed message are the ones that
    cryptographically bind the block: chain_id, height, hash, parent_hash,
    proposer, and state_root.
    """
    return {
        "chain_id": header.chain_id,
        "height": header.height,
        "hash": header.hash,
        "parent_hash": header.parent_hash,
        "proposer": header.proposer,
        "state_root": header.state_root,
    }


def validate_block_header(
    header: BridgeBlockHeader,
    validator_set: ValidatorSet | None = None,
) -> tuple[bool, str, str | None]:
    """Validate a block header's proposer signature.

    Args:
        header: The block header to validate.
        validator_set: Optional validator set for membership check.
            If provided, the recovered signer must be a member of the
            validator set's active addresses. If None, only signature
            validity is checked (not membership).

    Returns:
        ``(valid, error_message, recovered_address)``. If valid,
        ``error_message`` is empty and ``recovered_address`` is the
        checksum address of the signer. If invalid, ``recovered_address``
        may still be set (for non-member errors) or None (for signature
        errors).
    """
    if not header.signature:
        return False, "Block header has no signature", None

    message_data = build_verification_message(header)
    recovered = recover_signer(message_data, header.signature)
    if recovered is None:
        return False, "Invalid block header signature", None

    if validator_set is not None:
        # Case-insensitive membership check (recover_signer returns
        # checksum address, validator set may store lowercase)
        valid_addresses = {a.lower() for a in validator_set.addresses}
        if recovered.lower() not in valid_addresses:
            return False, f"Signer {recovered} not in validator set", recovered

    return True, "", recovered


def check_finality(
    header: BridgeBlockHeader,
    config: FinalityConfig,
    transfer_amount: int,
) -> tuple[bool, int]:
    """Check if a block header has sufficient finality for a transfer.

    Large transfers (>= ``config.large_transfer_threshold``) require full
    finality (``config.finality_blocks`` confirmations). Small transfers
    require only ``config.min_confirmations``.

    Args:
        header: The block header to check.
        config: Finality threshold configuration.
        transfer_amount: The transfer amount in compute-seconds.

    Returns:
        ``(has_finality, required_confirmations)``.
    """
    required = config.finality_blocks if transfer_amount >= config.large_transfer_threshold else config.min_confirmations
    return header.confirmation_count >= required, required
