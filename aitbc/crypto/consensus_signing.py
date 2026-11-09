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

from .signature_metrics import ERROR, MISMATCH, UNPARSEABLE, record_attempt, record_failure

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Consensus message signing (canonical-JSON + keccak256 + secp256k1)
# ---------------------------------------------------------------------------


def canonical_json(message: dict[str, Any]) -> bytes:
    """Serialize a message dict to canonical JSON bytes (UTF-8).

    Keys are sorted, separators are compact (no whitespace). This is
    THE shared canonical form: signer and verifier MUST serialize with
    exactly this function or scoped signature hashes disagree (#1128).
    Matches the format used by ``recover_signer()`` in ``crypto.py``.
    """
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode()


# Backwards-compatible private alias.
_canonical_json = canonical_json


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
    from .signature_recovery import canonical_address

    recovered = recover_signer(message, signature)
    if recovered is None:
        return False
    return canonical_address(recovered) == canonical_address(expected_sender)


# ---------------------------------------------------------------------------
# Domain-separated consensus signing (#1298 I3b — height-gated, inert until
# ``consensus_domain_separation_height`` is armed)
# ---------------------------------------------------------------------------

CONSENSUS_DOMAIN_V1 = "aitbc-consensus-v1"
DOMAIN_BLOCK_PROPOSAL = f"{CONSENSUS_DOMAIN_V1}:block_proposal"
DOMAIN_BLOCK_ATTESTATION = f"{CONSENSUS_DOMAIN_V1}:block_attestation"


def _domain_preimage(message: dict[str, Any], domain: str) -> bytes:
    """``keccak256(domain + ":" + canonical_json(message))``.

    Same convention as ``agent_envelope.domain_digest`` — the domain tag sits
    outside the payload so it cannot collide with a payload field and survives
    payload-schema evolution. Rebuilt locally to keep this module free of a
    cross-package import.
    """
    from eth_utils import keccak

    return keccak(domain.encode("utf-8") + b":" + _canonical_json(message))


def sign_consensus_message_domain(message: dict[str, Any], private_key: str, domain: str) -> str:
    """``sign_consensus_message`` over the domain-separated preimage.

    The signature verifies ONLY under ``domain`` — a proposal signature can
    never satisfy attestation verification and vice versa (#1298).
    """
    try:
        from eth_keys import keys

        pk_hex = private_key.removeprefix("0x")
        pk = keys.PrivateKey(bytes.fromhex(pk_hex))
        sig = pk.sign_msg_hash(_domain_preimage(message, domain))
        return sig.to_hex()
    except ImportError:
        raise ImportError(
            "eth-keys and eth-utils are required for consensus signing. Install with: pip install eth-keys eth-utils"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to sign domain-separated consensus message: {e}") from e


def verify_consensus_message_domain(
    message: dict[str, Any],
    signature: str,
    expected_sender: str,
    domain: str,
) -> bool:
    """Verify a signature produced by ``sign_consensus_message_domain``.

    Deliberately has NO legacy fallback: post-activation attestation
    verification must reject proposal-domain and pre-domain signatures.
    """
    if not signature:
        return False
    from .signature_recovery import SignatureMalformed, canonical_address, recover_address

    try:
        recovered = recover_address(_domain_preimage(message, domain), signature)
    except (SignatureMalformed, ValueError):
        return False
    return canonical_address(recovered) == canonical_address(expected_sender)


# ---------------------------------------------------------------------------
# Block header signing (canonical JSON + secp256k1)
# ---------------------------------------------------------------------------


def _block_header_message(block: Any) -> dict[str, Any]:
    """Build the canonical block header message from a dict or Block object."""

    def _get(name: str) -> Any:
        if isinstance(block, dict):
            return block.get(name)
        return getattr(block, name, None)

    return {
        "chain_id": _get("chain_id") or "",
        "height": _get("height") or 0,
        "hash": _get("hash") or "",
        "parent_hash": _get("parent_hash") or "",
        "proposer": _get("proposer") or "",
        "state_root": _get("state_root") or "",
        "bridge_state_root": _get("bridge_state_root") or "",
    }


def block_header_message(block: Any) -> dict[str, Any]:
    """Public accessor for the canonical 7-field header message (#1298 —
    domain-separated proposal verification rebuilds the identical dict)."""
    return _block_header_message(block)


def sign_block_hash(block: Any, private_key: str) -> str:
    """Sign a block header with a secp256k1 private key.

    v0.7.2: The signed message is the canonical-JSON encoding of the block
    header fields (chain_id, height, hash, parent_hash, proposer, state_root,
    bridge_state_root). This is the same format used by the bridge verifier.

    For backward compatibility, if ``block`` is a plain hex string it is
    treated as a legacy raw SHA-256 block hash and signed directly.
    """
    if isinstance(block, str):
        try:
            from eth_keys import keys

            pk_hex = private_key.removeprefix("0x")
            pk = keys.PrivateKey(bytes.fromhex(pk_hex))
            msg_hash = bytes.fromhex(block.removeprefix("0x"))
            sig = pk.sign_msg_hash(msg_hash)
            return sig.to_hex()
        except ImportError:
            raise ImportError("eth-keys is required for block signing. Install with: pip install eth-keys") from None
        except Exception as e:
            raise ValueError(f"Failed to sign block hash: {e}") from e

    return sign_consensus_message(_block_header_message(block), private_key)


def verify_block_signature(
    block: Any,
    signature: str,
    expected_proposer: str,
) -> bool:
    """Verify a block header signature against an expected proposer address.

    v0.7.2: The signature is verified against the canonical-JSON encoding of
    the block header fields. For backward compatibility, if ``block`` is a
    plain hex string the signature is verified against the raw SHA-256 block
    hash.
    """
    record_attempt("block")
    if not signature:
        record_failure("block", UNPARSEABLE)
        return False

    from .signature_recovery import SignatureMalformed, recover_address, verify_signature

    # Try the new canonical header format first.
    if not isinstance(block, str):
        try:
            if verify_consensus_message(_block_header_message(block), signature, expected_proposer):
                return True
        except Exception:
            pass

    # Fall back to legacy raw block-hash signing.
    if isinstance(block, str):
        block_hash = block
    elif isinstance(block, dict):
        block_hash = block.get("hash", "")
    else:
        block_hash = getattr(block, "hash", "")
    if not block_hash:
        record_failure("block", ERROR)
        return False

    try:
        msg_hash = bytes.fromhex(block_hash.removeprefix("0x"))
    except ValueError:
        logger.warning("Block hash is not valid hex, cannot verify signature")
        record_failure("block", ERROR)
        return False

    try:
        valid = verify_signature(msg_hash, signature, expected_proposer)
    except SignatureMalformed as e:
        logger.warning("Malformed block signature (encoding fault, not a failed check): %s", e)
        record_failure("block", UNPARSEABLE)
        return False

    if not valid:
        try:
            recovered = recover_address(msg_hash, signature)
        except (SignatureMalformed, ValueError):
            recovered = "<unrecoverable>"
        logger.warning(
            "Block signature does not match the declared proposer: recovered %s, expected %s",
            recovered,
            expected_proposer,
        )
        record_failure("block", MISMATCH)
    return valid
