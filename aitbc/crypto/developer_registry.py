"""Wallet-signature attestation for developer registry registration (#2566).

``POST /v1/developers`` used to accept any ``wallet_address`` — a client could
register a wallet it does not control into the DAO grant registry. The
registration now carries a secp256k1 signature over a domain-separated claim
binding ``wallet_address`` to every profile field plus a timestamp; the
server recovers the signer and refuses mismatches. The timestamp bounds how
long a captured signature stays usable; replaying it can only re-register
the same wallet, which the service already rejects as a duplicate.
"""

from __future__ import annotations

import time
from typing import Any, Final

DEVELOPER_REGISTER_DOMAIN: Final = "aitbc-developer-register-v1"

#: How far a registration timestamp may drift from server time (seconds).
DEVELOPER_REGISTER_MAX_AGE_SECONDS: Final = 600


def developer_register_claim(
    *,
    wallet_address: str,
    name: str | None,
    email: str | None,
    github_handle: str | None,
    timestamp: int,
) -> dict[str, Any]:
    """The canonical claim a developer-register signature covers.

    ``None`` profile fields normalize to ``""`` so the signer and verifier
    build byte-identical payloads regardless of which side omitted them.
    ``wallet_address`` is canonicalized to EIP-55: the server's schema
    validator lowercases the stored value, so signing the raw spelling
    would produce a different digest on each side (#2566).
    """
    from .signature_recovery import canonical_address

    return {
        "wallet_address": canonical_address(wallet_address),
        "name": name or "",
        "email": email or "",
        "github_handle": github_handle or "",
        "timestamp": timestamp,
    }


def developer_register_digest(claim: dict[str, Any]) -> bytes:
    """Domain-separated keccak256 digest of a registration claim."""
    from .agent_envelope import domain_digest

    return domain_digest(claim, DEVELOPER_REGISTER_DOMAIN)


def sign_developer_register(claim: dict[str, Any], private_key: str) -> str:
    """Sign a registration claim; returns the ``0x``-prefixed signature."""
    from .crypto import sign_transaction_hash

    return "0x" + sign_transaction_hash(developer_register_digest(claim).hex(), private_key).removeprefix("0x")


def verify_developer_register(claim: dict[str, Any], signature: str | None, expected_address: str) -> bool:
    """True iff ``signature`` over ``claim`` recovers to ``expected_address``."""
    from .signature_recovery import SignatureMalformed, verify_signature

    if not signature:
        return False
    try:
        return verify_signature(developer_register_digest(claim), signature, expected_address)
    except SignatureMalformed:
        return False


def developer_register_timestamp_fresh(timestamp: int, *, now: float | None = None) -> bool:
    """True iff ``timestamp`` is within the allowed clock-skew window."""
    current = time.time() if now is None else now
    return abs(current - float(timestamp)) <= DEVELOPER_REGISTER_MAX_AGE_SECONDS
