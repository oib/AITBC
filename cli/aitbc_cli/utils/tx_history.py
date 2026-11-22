"""Paged ``/rpc/transactions`` scans for payload-id lookups (#2507).

``bounty status`` and ``agent-staking status`` match rows client-side on
``payload.<key> == <id>``. The RPC answers newest-first and clamps ``limit``
to 500, so a single bounded page silently misses ids older than the window —
an existing bounty/stake read ``found:false``/empty. This helper walks the
type's history with the ``before_id`` cursor until the row budget is spent
or history is exhausted, and reports ``truncated`` so a capped scan is never
mistaken for not-found.
"""

from __future__ import annotations

from typing import Any

from .http_client import AITBCHTTPClient

# The RPC clamps `limit` to 500; page at the clamp and keep a hard page cap
# so a pathological history cannot turn one lookup into an unbounded scan.
SCAN_PAGE_SIZE = 500
SCAN_MAX_PAGES = 20  # 10 000 rows per tx type per lookup


def _rows_of(payload: Any) -> list[dict[str, Any]]:
    """Normalise the /rpc/transactions body: bare list or {"transactions": [...]} (#2241)."""
    if isinstance(payload, dict):
        payload = payload.get("transactions", [])
    return [r for r in (payload or []) if isinstance(r, dict)]


def scan_transactions_for_payload_id(
    client: AITBCHTTPClient,
    *,
    transaction_type: str,
    payload_key: str,
    payload_id: str,
    chain_id: str | None = None,
    limit: int = SCAN_PAGE_SIZE * SCAN_MAX_PAGES,
    page_size: int = SCAN_PAGE_SIZE,
    max_pages: int = SCAN_MAX_PAGES,
) -> tuple[list[dict[str, Any]], bool]:
    """Collect rows of ``transaction_type`` whose ``payload[payload_key]`` string-matches ``payload_id``.

    Pages newest->oldest with ``before_id`` = lowest ``transaction_id`` seen.
    Returns ``(matches, truncated)``; ``truncated`` is True when the row
    budget or page cap stopped the scan while older history may remain —
    callers MUST surface it rather than report the id as not-found.
    """
    matches: list[dict[str, Any]] = []
    scanned = 0
    before_id: int | None = None
    for _ in range(max_pages):
        want = min(page_size, max(1, limit) - scanned)
        if want <= 0:
            return matches, True
        params: dict[str, Any] = {"transaction_type": transaction_type, "limit": want}
        if chain_id:
            params["chain_id"] = chain_id
        if before_id is not None:
            params["before_id"] = before_id
        page = _rows_of(client.get_json("/rpc/transactions", params=params))
        if not page:
            return matches, False
        scanned += len(page)
        for row in page:
            payload = row.get("payload") or {}
            if isinstance(payload, dict) and str(payload.get(payload_key)) == payload_id:
                matches.append(row)
        ids = [tid for r in page if isinstance((tid := r.get("transaction_id")), int)]
        if not ids or len(page) < want:
            return matches, False
        before_id = min(ids)
        if scanned >= limit:
            # Last page was full — older rows may exist; say so.
            return matches, True
    return matches, True
