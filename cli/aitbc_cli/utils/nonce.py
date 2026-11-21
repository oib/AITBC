"""Nonce selection helpers for transaction submission (#2395)."""

from __future__ import annotations

from typing import Any, Protocol

from aitbc.exceptions import AITBCError

_MEMPOOL_PROBE_ERRORS = (AITBCError, ValueError, TypeError, AttributeError, KeyError)


class _HttpGet(Protocol):
    """Minimal surface the helpers need — satisfied by AITBCHTTPClient and
    test stubs alike."""

    def get(self, *args: Any, **kwargs: Any) -> Any: ...


def pending_nonce_floor(
    client: _HttpGet,
    sender_address: str,
    sealed_nonce: int,
    chain_id: str | None = None,
    limit: int = 500,
) -> int:
    """Next free nonce: ``max(sealed, highest pending mempool nonce + 1)``.

    The sealed account nonce ignores the sender's own in-flight transactions,
    so two back-to-back submits collide on the same nonce slot (#2395). A
    mempool probe miss (non-200, unreachable, malformed answer) degrades to
    ``sealed_nonce`` — same containment as the server-side
    ``_mempool_nonce_floor`` in escrow_routes_helpers.
    """
    try:
        query = f"limit={limit}"
        if chain_id:
            query += f"&chain_id={chain_id}"
        data = client.get(f"/rpc/mempool?{query}")
        transactions = data.get("transactions") if isinstance(data, dict) else None
        pending_nonces = [
            int(tx["nonce"])
            for tx in transactions or []
            if isinstance(tx, dict)
            and str(tx.get("from") or tx.get("sender") or "").lower() == sender_address.lower()
            and isinstance(tx.get("nonce"), int)
            and not isinstance(tx.get("nonce"), bool)
        ]
        if pending_nonces:
            return max(sealed_nonce, max(pending_nonces) + 1)
    except _MEMPOOL_PROBE_ERRORS:
        pass
    return sealed_nonce


def next_send_nonce(client: _HttpGet, sender_address: str, chain_id: str | None = None) -> int:
    """Sealed nonce plus the mempool lookahead for CLI-signed transactions.

    Raises when the sealed-nonce lookup itself fails — signing at a guessed
    nonce produces a transaction the chain refuses.
    """
    query = f"?chain_id={chain_id}" if chain_id else ""
    account = client.get(f"/rpc/account/{sender_address}{query}")
    if not isinstance(account, dict):
        raise ValueError(f"/rpc/account/{sender_address} returned a non-object response")
    nonce = account.get("nonce")
    if nonce is None:
        raise ValueError(f"/rpc/account/{sender_address} response carried no nonce")
    sealed = int(nonce)
    return pending_nonce_floor(client, sender_address, sealed, chain_id)
