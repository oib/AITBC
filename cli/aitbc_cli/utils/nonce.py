"""Nonce selection helpers for transaction submission (#2395)."""

from __future__ import annotations

from typing import Any, Protocol

from aitbc.exceptions import AITBCError

_MEMPOOL_PROBE_ERRORS = (AITBCError, ValueError, TypeError, AttributeError, KeyError)


class NonceClassificationError(RuntimeError):
    """The node could not prove which pending entries still occupy a nonce
    slot (#2745). Deliberately outside ``_MEMPOOL_PROBE_ERRORS``: an
    explicit retry must fail closed — never sign on an ambiguous view."""


class _HttpGet(Protocol):
    """Minimal surface the helpers need — satisfied by AITBCHTTPClient and
    test stubs alike."""

    def get(self, *args: Any, **kwargs: Any) -> Any: ...


def _valid_nonce_view_entry(tx: Any) -> bool:
    """Shape check for one entry of a *classified* nonce view (#2745).

    The node tags classified answers with ``nonce_view_complete: true``; a
    member that cannot name its sender and nonce cannot be proven to occupy
    (or free) a slot, so the whole view is untrustworthy.
    """
    if not isinstance(tx, dict):
        return False
    sender = tx.get("from") or tx.get("sender")
    nonce = tx.get("nonce")
    return isinstance(sender, str) and bool(sender.strip()) and type(nonce) is int and nonce >= 0


def _nonce_mempool_entries(data: Any, require_nonce_view: bool) -> Any:
    """Validate the mempool answer's nonce-view markers and return entries.

    ``nonce_view_complete`` is the node's (#2745) explicit verdict:
    ``True`` promises a classified, well-formed list — a failed ``success``,
    a non-list ``transactions`` or any malformed member makes the whole view
    untrustworthy. ``False`` or any other non-``None`` marker is a known
    "cannot classify" that must bypass every fallback for every caller.
    ``None`` (absent marker) is a legacy node: it ignored the opt-in
    parameter, so ordinary sends still count every unclassified occupant,
    while ``require_nonce_view`` refuses.
    """
    transactions = data.get("transactions") if isinstance(data, dict) else None
    complete = data.get("nonce_view_complete") if isinstance(data, dict) else None
    if complete is True:
        if (
            data.get("success") is not True
            or not isinstance(transactions, list)
            or not all(_valid_nonce_view_entry(tx) for tx in transactions)
        ):
            raise NonceClassificationError("Could not classify pending nonces; no transaction was signed")
    elif complete is not None:
        raise NonceClassificationError("Could not classify pending nonces; no transaction was signed")
    elif require_nonce_view:
        raise NonceClassificationError("Retry requires a node that supports the rejection-aware nonce view")
    return transactions


def pending_nonce_floor(
    client: _HttpGet,
    sender_address: str,
    sealed_nonce: int,
    chain_id: str | None = None,
    limit: int = 500,
    *,
    require_nonce_view: bool = False,
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

    The probe always requests the node's rejection-aware nonce view
    (#2745 ``?nonce_view=true``): entries whose exact hash the chain already
    rejected stop occupying their slot. Nodes predating the parameter
    ignore it and answer with the ordinary unmarked listing, which still
    counts every occupant — so ordinary sends keep working against them.
    ``require_nonce_view`` makes the read strict for explicit retries: an
    unclassifiable, malformed or legacy-node answer raises
    ``NonceClassificationError`` instead of falling back — a retry never
    signs on an ambiguous view.

    Returns None when the mempool probe itself failed (non-200, unreachable,
    malformed answer) — distinct from a successful probe that found nothing
    pending, which returns ``sealed_nonce`` (#2479). Callers that add a
    per-batch offset must only do so on the None path: a readable empty
    mempool means earlier batch entries already sealed and the offset would
    skip nonces. With ``require_nonce_view`` a probe failure raises
    ``NonceClassificationError`` for the same fail-closed reason.
    """
    try:
        query = f"limit={limit}&nonce_view=true"
        if chain_id:
            query += f"&chain_id={chain_id}"
        data = client.get(f"/rpc/mempool?{query}")
        transactions = _nonce_mempool_entries(data, require_nonce_view)
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
    except _MEMPOOL_PROBE_ERRORS as exc:
        if require_nonce_view:
            raise NonceClassificationError("Could not read pending nonces for retry; no transaction was signed") from exc
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
