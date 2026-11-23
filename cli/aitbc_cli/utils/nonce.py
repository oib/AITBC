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
) -> int | None:
    """Lowest signable nonce: the first nonce at or above ``sealed_nonce``
    that no pending mempool transaction occupies.

    The sealed account nonce ignores the sender's own in-flight transactions,
    so two back-to-back submits collide on the same nonce slot (#2395). The
    floor fills the *lowest* gap rather than jumping past the highest
    pending nonce (#2745): a stranded or dead entry ahead of a hole (e.g. a
    consensus-rejected resubmission still parked in a follower's mempool)
    must not push the next signature into future-nonce territory — apply
    seals nonces sequentially, so the hole is the only slot that can land.

    Returns None when the mempool probe itself failed (non-200, unreachable,
    malformed answer) — distinct from a successful probe that found nothing
    pending, which returns ``sealed_nonce`` (#2479). Callers that add a
    per-batch offset must only do so on the None path: a readable empty
    mempool means earlier batch entries already sealed and the offset would
    skip nonces.
    """
    try:
        query = f"limit={limit}"
        if chain_id:
            query += f"&chain_id={chain_id}"
        data = client.get(f"/rpc/mempool?{query}")
        transactions = data.get("transactions") if isinstance(data, dict) else None
        occupied = {
            int(tx["nonce"])
            for tx in transactions or []
            if isinstance(tx, dict)
            and str(tx.get("from") or tx.get("sender") or "").lower() == sender_address.lower()
            and isinstance(tx.get("nonce"), int)
            and not isinstance(tx.get("nonce"), bool)
        }
        nonce = sealed_nonce
        while nonce in occupied:
            nonce += 1
        return nonce
    except _MEMPOOL_PROBE_ERRORS:
        return None


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
    floor = pending_nonce_floor(client, sender_address, sealed, chain_id)
    return floor if floor is not None else sealed
