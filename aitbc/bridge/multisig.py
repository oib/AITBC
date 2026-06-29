"""Bridge multi-signature threshold verification (v0.7.1 §A2).

M-of-N threshold signature verification using secp256k1. Each validator
signs the proof independently; the bridge verifies that at least M of the
N validators in the current validator set signed the proof.

No BLS aggregation — each signature is verified individually using
``aitbc.crypto.crypto.recover_signer()``. This keeps the dependency surface
minimal (no new crypto libraries) and is sufficient for the validator set
sizes in AITBC (5-21 validators per chain).

The signed message is the canonical-JSON encoding of the proof fields
**excluding** the signature fields, matching the message format used by
``aitbc.bridge.proof.verify_proposer_signature`` for single-signer proofs.
This means a single-signer ``proposer_signature`` and a multi-sig
``validator_signatures`` entry over the same proof recover the same
address — enabling backward-compatible fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import ThresholdProof, ValidatorSet

logger = logging.getLogger(__name__)


def _proof_message_data(proof: ThresholdProof) -> dict[str, Any]:
    """Build the canonical message dict that validators sign.

    This is the proof without any signature fields. The ordering of keys
    does not matter — ``recover_signer`` re-serializes with
    ``sort_keys=True`` before hashing.
    """
    return {
        "source_chain": proof.source_chain,
        "lock_tx_hash": proof.lock_tx_hash,
        "amount": proof.amount,
        "sender": proof.sender,
        "recipient": proof.recipient,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
    }


def recover_all_signers(message_data: dict[str, Any], signatures: list[str]) -> list[str]:
    """Recover signer addresses from multiple signatures over the same message.

    Each signature is verified independently via ``recover_signer``. Invalid
    or empty signatures are skipped (not included in the result). Duplicate
    recovered addresses are preserved here — deduplication happens in
    :func:`check_threshold`.

    Returns:
        List of recovered checksum addresses (in signature order, skipping
        invalid entries).
    """
    signers: list[str] = []
    for sig in signatures:
        if not sig:
            continue
        addr = recover_signer(message_data, sig)
        if addr:
            signers.append(addr)
    return signers


def check_threshold(
    signers: list[str],
    validator_set: ValidatorSet,
    threshold: int | None = None,
) -> tuple[bool, int, list[str]]:
    """Check if enough signers are in the validator set to meet threshold.

    Args:
        signers: Recovered signer addresses (may contain duplicates or
            non-members).
        validator_set: The validator set to check membership against.
        threshold: Override threshold (defaults to ``validator_set.threshold``).

    Returns:
        ``(meets_threshold, valid_signer_count, valid_signer_addresses)``.
        Duplicate signers are deduplicated (one signer cannot count twice).
        Non-members are filtered out before counting.
    """
    required = threshold if threshold is not None else validator_set.threshold
    valid_addresses = validator_set.addresses
    valid_signers = [s for s in signers if s in valid_addresses]
    # Deduplicate (one signer can't count twice)
    unique_signers = list(dict.fromkeys(valid_signers))
    return len(unique_signers) >= required, len(unique_signers), unique_signers


def verify_threshold_signatures(
    proof: ThresholdProof,
    validator_set: ValidatorSet,
    threshold: int | None = None,
) -> tuple[bool, int, list[str]]:
    """Verify that a proof has enough valid validator signatures to meet threshold.

    Builds the signed message from the proof fields (excluding signature
    fields), collects all signatures (validator sigs + backward-compat
    proposer sig), recovers each signer via ``recover_signer``, and checks
    the threshold against the validator set.

    Backward-compatible: if ``validator_signatures`` is empty, falls back to
    the single ``proposer_signature`` — yielding a 1-signer proof that will
    only meet threshold if the threshold is 1.

    Returns:
        ``(meets_threshold, valid_signer_count, valid_signer_addresses)``.
    """
    message_data = _proof_message_data(proof)

    # Collect all signatures (validator sigs + backward-compat proposer sig)
    all_sigs = list(proof.validator_signatures)
    if proof.proposer_signature and proof.proposer_signature not in all_sigs:
        all_sigs.append(proof.proposer_signature)

    signers = recover_all_signers(message_data, all_sigs)
    return check_threshold(signers, validator_set, threshold)
