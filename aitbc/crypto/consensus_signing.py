"""Consensus message signing and verification utilities (v0.7.5 §A1).

Provides secp256k1 signing/verification for consensus messages (PBFT
pre-prepare/prepare/commit, votes, slashing evidence) and block hashes.
These are the shared utilities that ``MultiValidatorPoA`` and
``PBFTConsensus`` in ``apps/blockchain-node/`` use to sign and verify
all consensus-critical data.

Two signing modes:

1. **Consensus messages** (dict-based) — canonical-JSON serialized,
   keccak256-hashed, signed with secp256k1. This is the counterpart to
   ``recover_signer()`` in ``crypto.py`` — the signing function that
   was missing. Used for PBFT messages, votes, slashing evidence.

2. **Block hashes** (raw hash) — the block hash (already a SHA-256 hex
   string) is treated as a message hash and signed directly with
   ``eth_keys.PrivateKey.sign_msg_hash()``. This matches the pattern in
   ``poa.py:_sign_block_hash()`` and ``poa.py:verify_block_signature()``
   — the shared utility version so MultiValidatorPoA doesn't need to
   duplicate that code.

All functions use ``eth_keys`` (not ``eth_account``) for consistency
with the existing block signing infrastructure and lighter weight.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Consensus message signing (canonical-JSON + keccak256 + secp256k1)
# ---------------------------------------------------------------------------


def _canonical_json(message: dict[str, Any]) -> bytes:
    """Serialize a message dict to canonical JSON bytes.

    Keys are sorted, separators are compact (no whitespace). This
    matches the format used by ``recover_signer()`` in ``crypto.py``.
    """
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode()


def sign_consensus_message(message: dict[str, Any], private_key: str) -> str:
    """Sign a consensus message with a secp256k1 private key.

    The message dict is canonical-JSON serialized, keccak256-hashed, and
    signed with ``eth_keys``. The signature is the counterpart to
    ``recover_signer()`` — it can be verified with
    ``verify_consensus_message()`` or by calling ``recover_signer()``
    directly.

    Args:
        message: The dict to sign. Must not contain a ``signature`` key
            (the signature is computed over the message without it).
        private_key: Hex-encoded secp256k1 private key (with or without
            ``0x`` prefix).

    Returns:
        65-byte hex signature string (``r‖s‖v``, no ``0x`` prefix).

    Raises:
        ValueError: If signing fails (invalid key, etc.).
        ImportError: If ``eth_keys`` or ``eth_utils`` are not installed.
    """
    try:
        from eth_keys import keys
        from eth_utils import keccak

        pk_hex = private_key.removeprefix("0x")
        pk = keys.PrivateKey(bytes.fromhex(pk_hex))
        msg_bytes = _canonical_json(message)
        msg_hash = keccak(msg_bytes)
        sig = pk.sign_msg_hash(msg_hash)
        return sig.to_hex()
    except ImportError:
        raise ImportError(
            "eth-keys and eth-utils are required for consensus signing. Install with: pip install eth-keys eth-utils"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to sign consensus message: {e}") from e


def verify_consensus_message(
    message: dict[str, Any],
    signature: str,
    expected_sender: str,
) -> bool:
    """Verify a consensus message signature.

    Args:
        message: The dict that was signed (without ``signature`` key).
        signature: The 65-byte hex signature from ``sign_consensus_message()``.
        expected_sender: The Ethereum address (checksum or lowercase) of
            the expected signer.

    Returns:
        True if the signature is valid and recovers to ``expected_sender``.
        False if the signature is empty, invalid, or recovers to a
        different address.
    """
    if not signature:
        return False
    from .crypto import recover_signer

    recovered = recover_signer(message, signature)
    if recovered is None:
        return False
    return recovered.lower() == expected_sender.lower()


# ---------------------------------------------------------------------------
# Block hash signing (raw hash + secp256k1)
# ---------------------------------------------------------------------------


def sign_block_hash(block_hash: str, private_key: str) -> str:
    """Sign a block hash with a secp256k1 private key.

    The block hash (a SHA-256 hex string) is treated as a message hash
    and signed directly with ``eth_keys.PrivateKey.sign_msg_hash()``.
    This matches the pattern in ``poa.py:_sign_block_hash()`` — the
    shared utility version so MultiValidatorPoA doesn't duplicate it.

    Args:
        block_hash: Hex-encoded block hash (with or without ``0x`` prefix).
        private_key: Hex-encoded secp256k1 private key (with or without
            ``0x`` prefix).

    Returns:
        65-byte hex signature string (``r‖s‖v``, no ``0x`` prefix).

    Raises:
        ValueError: If signing fails (invalid key, invalid hash, etc.).
        ImportError: If ``eth_keys`` is not installed.
    """
    try:
        from eth_keys import keys

        pk_hex = private_key.removeprefix("0x")
        pk = keys.PrivateKey(bytes.fromhex(pk_hex))
        msg_hash = bytes.fromhex(block_hash.removeprefix("0x"))
        sig = pk.sign_msg_hash(msg_hash)
        return sig.to_hex()
    except ImportError:
        raise ImportError("eth-keys is required for block signing. Install with: pip install eth-keys") from None
    except Exception as e:
        raise ValueError(f"Failed to sign block hash: {e}") from e


def verify_block_signature(
    block_hash: str,
    signature: str,
    expected_proposer: str,
) -> bool:
    """Verify a block signature against an expected proposer address.

    This matches the pattern in ``poa.py:verify_block_signature()`` —
    the shared utility version so MultiValidatorPoA's ``validate_block()``
    (C1 fix) can call it without depending on ``apps/blockchain-node/``.

    Args:
        block_hash: Hex-encoded block hash (with or without ``0x`` prefix).
        signature: 65-byte hex signature from ``sign_block_hash()``.
        expected_proposer: The Ethereum address of the expected proposer.

    Returns:
        True if the signature is valid and recovers to
        ``expected_proposer``. False if the signature is empty, invalid,
        wrong length, or recovers to a different address.
    """
    if not signature:
        return False
    try:
        from eth_keys import keys

        msg_hash = bytes.fromhex(block_hash.removeprefix("0x"))
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        if len(sig_bytes) != 65:
            return False
        sig = keys.Signature(sig_bytes)
        pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
        recovered = pub_key.to_checksum_address()
        return recovered.lower() == expected_proposer.lower()
    except Exception:
        return False
