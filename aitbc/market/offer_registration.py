"""Signed software-offer registration.

POST /v1/market/offer is publicly reachable and historically accepted any
caller, so a local SoftwareService row could claim another provider's
plugin_id and provider_address — squatting their identity in the merged
listing and inheriting their on-chain anchors. Registration now requires a
secp256k1 signature from the claimed ``provider_address`` over the
registration's identity fields (the same canonical-JSON signature every
signed transaction uses), a fresh ``issued_at``, and the market's
``chain_id`` so a signature captured elsewhere cannot replay.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.crypto import recover_signer
from aitbc.crypto.signature_recovery import canonical_address

# Registration signatures are single-use proofs, not session credentials:
# a short clock window bounds replay without a server-side nonce store.
REGISTRATION_MAX_AGE_SECONDS = 300


def registration_message(
    action: str, plugin_id: str, provider_address: str, chain_id: str, issued_at: int
) -> dict[str, Any]:
    """Canonical fields a provider signs for offer registration.

    ``action`` scopes the proof so a captured signature cannot be reused for
    a different operation (e.g. a future signed unregister).
    """
    return {
        "action": action,
        "plugin_id": plugin_id,
        "provider_address": provider_address,
        "chain_id": chain_id,
        "issued_at": issued_at,
    }


def verify_offer_registration(
    data: dict[str, Any],
    expected_chain_id: str,
    *,
    action: str = "register",
    now: float | None = None,
    max_age_seconds: int = REGISTRATION_MAX_AGE_SECONDS,
) -> str | None:
    """Validate the registration signature carried in ``data``.

    Returns an error string describing the rejection, or None when the
    signature is valid. ``data`` must carry ``plugin_id``,
    ``provider_address``, ``chain_id``, ``issued_at`` and ``signature``;
    the signed message is the canonical registration_message over the rest,
    which keeps ``signature`` itself out of the signed bytes.
    """
    plugin_id = str(data.get("plugin_id") or "")
    provider = str(data.get("provider_address") or "")
    chain_id = str(data.get("chain_id") or "")
    issued_at = data.get("issued_at")
    signature = data.get("signature")
    if not provider:
        return "provider_address is required"
    if not chain_id:
        return "chain_id is required for offer registration"
    if expected_chain_id and chain_id != expected_chain_id:
        return f"chain_id '{chain_id}' does not match this market's chain '{expected_chain_id}'"
    if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
        return "issued_at (epoch seconds) is required for offer registration"
    if int(issued_at) != issued_at:
        return "issued_at must be an integer number of epoch seconds"
    now = time.time() if now is None else now
    if abs(now - issued_at) > max_age_seconds:
        return "issued_at is outside the accepted clock window"
    if not signature:
        return "signature is required for offer registration"
    message = registration_message(action, plugin_id, provider, chain_id, int(issued_at))
    recovered = recover_signer(message, str(signature))
    if recovered is None:
        return "invalid offer registration signature"
    if canonical_address(recovered) != canonical_address(provider):
        return f"offer registration signature does not match provider_address {provider}"
    return None
