"""Job-party request signing for market mutations (#1893/#1907).

The market service's object-scoped mutation routes (jobs release/refund/
dispute/cancel, offer book/cancel) reject unsigned user-key requests with
403 — a job-party wallet signature or the operator credential is required.
This module signs the canonical ``jobs_request_message`` for a route with
the resolved market wallet, reusing the same scheme ``market cancel``
already uses.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.crypto import sign_transaction_data
from aitbc.market.job_request_signature import jobs_request_message

from ...utils import warning


def signed_job_request_fields(
    ctx,
    route: str,
    *,
    wallet: tuple[str, str | None, str] | None = None,
) -> dict[str, Any]:
    """Return the signature fields a party-gated market route expects.

    ``route`` is the exact path the signature is bound to, e.g.
    ``/v1/market/jobs/<id>/release``. Signs with ``wallet`` when given
    (a ``load_wallet_for_payment``/``get_market_wallet`` triple), else the
    market wallet resolved from the command context. Returns ``{}`` when no
    private key is resolvable — the server then requires the operator
    credential, so callers should warn that the request will 403 for
    ordinary user-key callers.
    """
    # Lazy import: this module is loaded by market submodules during the
    # package __init__, so a top-level `from . import ...` would close an
    # import cycle.
    from . import get_chain_id, get_market_wallet

    try:
        resolved = wallet if wallet is not None else get_market_wallet(ctx, require_private_key=False)
        address, private_key, _ = resolved
        if not (address and private_key):
            return {}
        chain_id = get_chain_id()
        if not chain_id:
            return {}
        issued_at = int(time.time())
        message = jobs_request_message(address, chain_id, issued_at, route)
        return {
            "signer_address": address,
            "chain_id": chain_id,
            "issued_at": issued_at,
            "signature": sign_transaction_data(message, private_key),
        }
    except Exception as e:  # noqa: BLE001 - unsigned request is rejected server-side (#1893)
        warning(f"Could not sign market request for {route}: {e}")
        return {}
