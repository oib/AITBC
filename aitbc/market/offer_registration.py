"""Signed software-offer registration.

POST /v1/market/offer is publicly reachable and historically accepted any
caller, so a local SoftwareService row could claim another provider's
plugin_id and provider_address — squatting their identity in the merged
listing and inheriting their on-chain anchors. Registration now requires a
secp256k1 signature from the claimed ``provider_address`` over the
registration's identity fields plus ``offer_hash``, a digest of the entire
request body (the same canonical-JSON signature every signed transaction
uses). The recovered signer must equal ``provider_address``, ``issued_at``
must sit inside a short window, and ``chain_id`` must match the market's
chain so a captured signature cannot replay elsewhere — while offer_hash
ties the proof to exactly this offer, so reuse can only repeat the
identical registration.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from aitbc.crypto.crypto import recover_signer
from aitbc.crypto.signature_recovery import canonical_address

# Registration signatures are single-use proofs, not session credentials:
# a short clock window bounds replay without a server-side nonce store.
REGISTRATION_MAX_AGE_SECONDS = 300


def offer_body_hash(body: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the request body, minus ``signature``.

    The hash binds the signature to the offer's contents — price, endpoint,
    capabilities — not just its identity, so a signature observed inside its
    validity window cannot be resubmitted under a different offer body.
    """
    unsigned = {k: v for k, v in body.items() if k != "signature"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def registration_message(
    action: str, plugin_id: str, provider_address: str, chain_id: str, issued_at: int, offer_hash: str
) -> dict[str, Any]:
    """Canonical fields a provider signs for offer registration.

    ``action`` scopes the proof so a captured signature cannot be reused for
    a different operation (e.g. a future signed unregister); ``offer_hash``
    binds it to the exact request body.
    """
    return {
        "action": action,
        "plugin_id": plugin_id,
        "provider_address": provider_address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "offer_hash": offer_hash,
    }


def verify_offer_registration(
    data: dict[str, Any],
    expected_chain_id: str,
    *,
    action: str = "register",
    now: float | None = None,
    max_age_seconds: int = REGISTRATION_MAX_AGE_SECONDS,
) -> tuple[str | None, str | None]:
    """Validate the registration signature carried in ``data``.

    Returns ``(error, signer)``: ``error`` is a string describing the
    rejection (``signer`` then None), or both are None-free — ``error`` None
    and ``signer`` the recovered checksummed provider address — when the
    signature is valid. The caller needs the signer to authorize updates to
    an existing row, which must belong to the same provider.

    ``data`` must carry ``plugin_id``, ``provider_address``, ``chain_id``,
    ``issued_at`` and ``signature``; the signed message is the canonical
    registration_message over the rest, which keeps ``signature`` itself out
    of the signed bytes.
    """
    plugin_id = str(data.get("plugin_id") or "")
    provider = str(data.get("provider_address") or "")
    chain_id = str(data.get("chain_id") or "")
    issued_at = data.get("issued_at")
    signature = data.get("signature")
    if not provider:
        return ("provider_address is required", None)
    if not chain_id:
        return ("chain_id is required for offer registration", None)
    if expected_chain_id and chain_id != expected_chain_id:
        return (f"chain_id '{chain_id}' does not match this market's chain '{expected_chain_id}'", None)
    if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
        return ("issued_at (epoch seconds) is required for offer registration", None)
    if int(issued_at) != issued_at:
        return ("issued_at must be an integer number of epoch seconds", None)
    now = time.time() if now is None else now
    if abs(now - issued_at) > max_age_seconds:
        return ("issued_at is outside the accepted clock window", None)
    if not signature:
        return ("signature is required for offer registration", None)
    digest = offer_body_hash(data)
    message = registration_message(action, plugin_id, provider, chain_id, int(issued_at), digest)
    recovered = recover_signer(message, str(signature))
    if recovered is None:
        return ("invalid offer registration signature", None)
    if canonical_address(recovered) != canonical_address(provider):
        return (f"offer registration signature does not match provider_address {provider}", None)
    return (None, recovered)
