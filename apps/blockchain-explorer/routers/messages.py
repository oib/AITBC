"""Read-only forum-message proxies (MSG-4).

Mirrors the chain RPC's ``/rpc/messaging/*`` read surface so the website can
reach it through the ``/explorer-api/`` nginx location. No write routes —
posting stays a signed ``MESSAGE`` transaction through ``/rpc/transaction``
(``aitbc messaging send``); nothing here opens the chain DB.

Bounds match the upstream handlers in ``aitbc_chain.rpc.messaging``: ``limit``
clamps to ``1..MAX_READ_LIMIT`` and ``offset`` rejects past ``MAX_OFFSET`` with
the same 400 wording; cursor validation stays upstream so cursor semantics have
a single implementation.
"""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger

from chain_client import BLOCKCHAIN_RPC_URLS, DEFAULT_CHAIN

logger = get_logger(__name__)
router = APIRouter()

# Mirrors aitbc_chain.messaging_index — keep the numbers identical so the
# explorer layer never widens what the index is willing to scan.
MAX_READ_LIMIT = 100
MAX_OFFSET = 500


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_READ_LIMIT))


def _check_offset(offset: int) -> None:
    if offset < 0 or offset > MAX_OFFSET:
        raise HTTPException(status_code=400, detail=f"offset must be 0..{MAX_OFFSET}")


async def _proxy(subpath: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET the upstream route; pass its status and detail through on non-200."""
    chain_id = params.pop("chain_id", None)
    params = {k: v for k, v in params.items() if v is not None}
    params["chain_id"] = chain_id or DEFAULT_CHAIN
    rpc_url = BLOCKCHAIN_RPC_URLS.get(chain_id or DEFAULT_CHAIN, BLOCKCHAIN_RPC_URLS[DEFAULT_CHAIN])
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{rpc_url}/rpc/messaging/{subpath}", params=params, timeout=10.0)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail="Messaging index unreachable") from e
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except ValueError:
            detail = resp.text[:200]
        raise HTTPException(status_code=resp.status_code, detail=detail)
    result = resp.json()
    return result if isinstance(result, dict) else {"result": result}


@router.get("/api/messages/state")
async def api_messages_state(chain_id: str | None = DEFAULT_CHAIN) -> dict[str, Any]:
    return await _proxy("state", {"chain_id": chain_id})


@router.get("/api/messages/topics")
async def api_messages_topics(
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = DEFAULT_CHAIN,
) -> dict[str, Any]:
    _check_offset(offset)
    return await _proxy(
        "topics",
        {"limit": _clamp_limit(limit), "offset": offset, "chain_id": chain_id},
    )


@router.get("/api/messages")
async def api_messages(
    topic: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    chain_id: str | None = DEFAULT_CHAIN,
) -> dict[str, Any]:
    """Newest-first message page; ``cursor`` takes a previous ``next_cursor``."""
    _check_offset(offset)
    return await _proxy(
        "messages",
        {
            "topic": topic,
            "limit": _clamp_limit(limit),
            "offset": offset,
            "cursor": cursor,
            "chain_id": chain_id,
        },
    )
