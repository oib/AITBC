"""Domain-separated secp256k1 envelopes for coordinator agent messages.

Implements the shared signing convention of
``docs/agent-coordinator/agent-signed-envelopes.md`` (§4/§5): a signature is
secp256k1 over ``keccak256("<domain>:" + canonical_json(payload))`` where the
canonical JSON uses sorted keys, compact separators and UTF-8 — the same
convention as :func:`aitbc.crypto.crypto.sign_transaction_data` and
:func:`aitbc.crypto.crypto.recover_signer`, plus a mandatory domain prefix so a
message signature cannot be replayed as a transaction signature (or vice
versa).

Recovery goes through :mod:`aitbc.crypto.signature_recovery`. Per V23-05 a
second ``eth_keys`` ``Signature`` call site is a test failure, not a style
choice — do not inline recovery here.
"""

from __future__ import annotations

import json
from typing import Any, Final

#: ``signature_version`` value written onto every signed envelope. The digest
#: domain prefix reuses it so the version string and the signed bytes cannot
#: diverge silently.
AGENT_MSG_SIGNATURE_VERSION: Final = "aitbc-agent-msg-v1"

#: Domain prefixes for the three signed object types. Message envelopes and
#: registry identity claims live in different domains so a registration proof
#: cannot be replayed as a message signature.
AGENT_MSG_DOMAIN: Final = AGENT_MSG_SIGNATURE_VERSION
AGENT_IDENTITY_DOMAIN: Final = "aitbc-agent-identity-v1"
AGENT_ROTATION_DOMAIN: Final = "aitbc-agent-rotation-v1"


def _canonical_json(payload: dict[str, Any]) -> bytes:
    """The repo's canonical-JSON convention: sorted keys, compact separators."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def domain_digest(payload: dict[str, Any], domain: str) -> bytes:
    """Return ``keccak256(domain + ":" + canonical_json(payload))``."""
    from eth_utils import keccak

    return keccak(domain.encode("utf-8") + b":" + _canonical_json(payload))


def _sign_digest(digest: bytes, private_key: str) -> str:
    """Sign a 32-byte digest; returns the ``0x``-prefixed 65-byte signature."""
    from .crypto import sign_transaction_hash

    return "0x" + sign_transaction_hash(digest.hex(), private_key).removeprefix("0x")


def _recover(digest: bytes, signature: str | None) -> str | None:
    """Recover the signer of ``digest`` or ``None`` on any decode failure."""
    from .signature_recovery import SignatureMalformed, recover_address

    if not signature:
        return None
    try:
        return recover_address(digest, signature)
    except SignatureMalformed:
        return None


def _matches(recovered: str | None, expected_address: str | None) -> bool:
    if recovered is None or not expected_address:
        return False
    from .signature_recovery import canonical_address

    return canonical_address(recovered) == canonical_address(expected_address)


# --- Message envelopes (§4) -------------------------------------------------


def envelope_digest(payload: dict[str, Any]) -> bytes:
    """Digest of an envelope signing payload (the envelope minus ``signature``)."""
    return domain_digest(payload, AGENT_MSG_DOMAIN)


def sign_agent_envelope(payload: dict[str, Any], private_key: str) -> str:
    """Sign an envelope signing payload; returns the ``0x``-prefixed signature."""
    return _sign_digest(envelope_digest(payload), private_key)


def recover_agent_envelope_signer(payload: dict[str, Any], signature: str | None) -> str | None:
    """Recover the EIP-55 signer of an envelope payload, or ``None``."""
    return _recover(envelope_digest(payload), signature)


def verify_agent_envelope(payload: dict[str, Any], signature: str | None, expected_address: str | None) -> bool:
    """True iff ``signature`` over ``payload`` recovers to ``expected_address``."""
    return _matches(recover_agent_envelope_signer(payload, signature), expected_address)


# --- Registry identity claims (§3) ------------------------------------------


def identity_claim(
    agent_id: str,
    identity_address: str,
    chain_id: str,
    nonce: str,
    registered_at: str,
) -> dict[str, Any]:
    """The canonical registration binding claim ``identity_proof`` signs.

    The dict is signed with :func:`sign_identity_claim`; the coordinator
    rebuilds it field-for-field from the registration request and requires the
    recovered signer to equal ``identity_address``.
    """
    return {
        "agent_id": agent_id,
        "identity_address": identity_address,
        "chain_id": chain_id,
        "nonce": nonce,
        "registered_at": registered_at,
    }


def identity_claim_digest(claim: dict[str, Any]) -> bytes:
    return domain_digest(claim, AGENT_IDENTITY_DOMAIN)


def sign_identity_claim(claim: dict[str, Any], private_key: str) -> str:
    """Sign a registration binding claim; returns the ``0x``-prefixed signature."""
    return _sign_digest(identity_claim_digest(claim), private_key)


def verify_identity_claim(claim: dict[str, Any], signature: str | None, expected_address: str | None) -> bool:
    """True iff ``signature`` over ``claim`` recovers to ``expected_address``."""
    return _matches(_recover(identity_claim_digest(claim), signature), expected_address)


# --- Identity rotation claims (§7) ------------------------------------------


def rotation_claim(
    agent_id: str,
    old_address: str,
    new_address: str,
    timestamp: str,
) -> dict[str, Any]:
    """The canonical rotation claim the *old* key signs to authorise a rebind."""
    return {
        "agent_id": agent_id,
        "new_address": new_address,
        "old_address": old_address,
        "timestamp": timestamp,
    }


def rotation_claim_digest(claim: dict[str, Any]) -> bytes:
    return domain_digest(claim, AGENT_ROTATION_DOMAIN)


def sign_rotation_claim(claim: dict[str, Any], private_key: str) -> str:
    """Sign a rotation claim; returns the ``0x``-prefixed signature."""
    return _sign_digest(rotation_claim_digest(claim), private_key)


def verify_rotation_claim(claim: dict[str, Any], signature: str | None, expected_address: str | None) -> bool:
    """True iff ``signature`` over ``claim`` recovers to ``expected_address``."""
    return _matches(_recover(rotation_claim_digest(claim), signature), expected_address)


__all__ = [
    "AGENT_IDENTITY_DOMAIN",
    "AGENT_MSG_DOMAIN",
    "AGENT_MSG_SIGNATURE_VERSION",
    "AGENT_ROTATION_DOMAIN",
    "domain_digest",
    "envelope_digest",
    "identity_claim",
    "identity_claim_digest",
    "recover_agent_envelope_signer",
    "rotation_claim",
    "rotation_claim_digest",
    "sign_agent_envelope",
    "sign_identity_claim",
    "sign_rotation_claim",
    "verify_agent_envelope",
    "verify_identity_claim",
    "verify_rotation_claim",
]
