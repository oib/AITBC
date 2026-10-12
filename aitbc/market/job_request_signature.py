"""Signed read-side proofs for market job routes.

``GET /v1/market/jobs`` and ``GET /v1/market/jobs/{job_id}`` answer anonymous
callers with a redacted public view: customer file details and rental
identifiers (``payload.cid``, ``payload.file_name``, ``buyer_address``,
``access_key``/``access_secret`` and friends) never leave the service
unauthenticated.

A caller that wants the full record proves control of an address with a
secp256k1 signature over a canonical message — the same canonical-JSON scheme
every signed transaction and offer registration uses. The message binds the
claimed address, the chain id, a freshness timestamp, and the exact route, so
a captured signature cannot be replayed against another endpoint, another
chain, or after a short clock window. Recovered signers receive full rows
only for jobs they are a party to — as ``buyer_address`` or
``provider_address`` — which is how the provider-side IPFS pinning sweeper
keeps reading ``payload.cid`` after the public feed stopped carrying it.

The credential is the provider/buyer wallet itself; nothing new is issued and
nothing is stored server-side.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.crypto import recover_signer
from aitbc.crypto.signature_recovery import canonical_address

# Signed requests are point-in-time proofs, not session credentials: a short
# clock window bounds replay without a server-side nonce store. abs() admits
# client clocks ahead of the server up to the same bound (skew allowance).
JOBS_REQUEST_MAX_AGE_SECONDS = 300


def jobs_request_message(signer_address: str, chain_id: str, issued_at: int, route: str) -> dict[str, Any]:
    """Canonical fields a buyer/provider signs to read their own job rows.

    ``route`` is the concrete request path (``/v1/market/jobs`` or
    ``/v1/market/jobs/<id>[/pin-confirm]``) so a proof minted for one endpoint
    cannot be reused on another.
    """
    return {
        "signer_address": signer_address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "route": route,
    }


def verify_jobs_request_signature(
    signer_address: str | None,
    chain_id: str | None,
    issued_at: int | float | None,
    route: str,
    signature: str | None,
    expected_chain_id: str,
    *,
    now: float | None = None,
    max_age_seconds: int = JOBS_REQUEST_MAX_AGE_SECONDS,
) -> tuple[str | None, str | None]:
    """Validate a signed market-jobs request.

    Returns ``(error, signer)``: ``error`` describes the rejection (``signer``
    is then None), or ``error`` is None and ``signer`` is the recovered
    checksummed address. The caller compares ``signer`` to the job's buyer or
    provider address — this function only proves key control.
    """
    if not signer_address:
        return ("signer_address is required", None)
    if not chain_id:
        return ("chain_id is required for a signed job request", None)
    if expected_chain_id and chain_id != expected_chain_id:
        return (f"chain_id '{chain_id}' does not match this market's chain '{expected_chain_id}'", None)
    if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
        return ("issued_at (epoch seconds) is required", None)
    if int(issued_at) != issued_at:
        return ("issued_at must be an integer number of epoch seconds", None)
    now = time.time() if now is None else now
    if abs(now - issued_at) > max_age_seconds:
        return ("issued_at is outside the accepted clock window", None)
    if not signature:
        return ("signature is required", None)
    message = jobs_request_message(signer_address, chain_id, int(issued_at), route)
    recovered = recover_signer(message, signature)
    if recovered is None:
        return ("invalid job request signature", None)
    if canonical_address(recovered) != canonical_address(signer_address):
        return ("job request signature does not match signer_address", None)
    return (None, recovered)
