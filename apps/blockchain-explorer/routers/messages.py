"""Read-only forum-message proxies (MSG-4, extended by MSG-17).

Mirrors the chain RPC's ``/rpc/messaging/*`` read surface so the website can
reach it through the ``/explorer-api/`` nginx location. No write routes —
posting stays a signed ``MESSAGE`` transaction through ``/rpc/transaction``
(``aitbc messaging send``); nothing here opens the chain DB.

Bounds match the upstream handlers in ``aitbc_chain.rpc.messaging``: ``limit``
clamps to ``1..MAX_READ_LIMIT`` and ``offset`` rejects past ``MAX_OFFSET`` with
the same 400 wording; cursor validation stays upstream so cursor semantics have
a single implementation.
"""

import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger

from chain_client import default_chain_id, rpc_url_for

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


# Path segments are interpolated into the upstream URL — an unvalidated
# segment could climb with `..` or smuggle a query with `?`. Each value must
# match the shape the upstream handler expects; anything else is a 400 here
# and never reaches the RPC. Patterns mirror aitbc.messaging.normalize_topic
# (canonical slug charset) and the chain's hex-hash/address formats.
_TX_HASH_RE = re.compile(r"(?:0x)?[0-9a-fA-F]{64}")
_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
_SLUG_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")


def _check_tx_hash(tx_hash: str) -> str:
    if not _TX_HASH_RE.fullmatch(tx_hash):
        raise HTTPException(status_code=400, detail=f"'{tx_hash}' is not a transaction hash")
    return tx_hash


def _check_address(address: str) -> str:
    if not _ADDRESS_RE.fullmatch(address):
        raise HTTPException(status_code=400, detail=f"'{address}' is not an address")
    return address


def _check_slug(slug: str) -> str:
    if not (1 <= len(slug) <= 64) or not _SLUG_RE.fullmatch(slug):
        raise HTTPException(status_code=400, detail=f"topic '{slug}' is not a valid slug")
    return slug


async def _proxy(subpath: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET the upstream route; pass its status and detail through on non-200."""
    chain_id = params.pop("chain_id", None)
    params = {k: v for k, v in params.items() if v is not None}
    resolved = chain_id or default_chain_id()
    params["chain_id"] = resolved
    rpc_url = rpc_url_for(resolved)
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
async def api_messages_state(chain_id: str | None = None) -> dict[str, Any]:
    return await _proxy("state", {"chain_id": chain_id})


@router.get("/api/messages/topics")
async def api_messages_topics(
    limit: int = 50,
    offset: int = 0,
    chain_id: str | None = None,
) -> dict[str, Any]:
    _check_offset(offset)
    return await _proxy(
        "topics",
        {"limit": _clamp_limit(limit), "offset": offset, "chain_id": chain_id},
    )


@router.get("/api/messages")
async def api_messages(
    topic: str | None = None,
    author: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    """Newest-first message page; ``cursor`` takes a previous ``next_cursor``."""
    _check_offset(offset)
    return await _proxy(
        "messages",
        {
            "topic": topic,
            "author": author,
            "limit": _clamp_limit(limit),
            "offset": offset,
            "cursor": cursor,
            "chain_id": chain_id,
        },
    )


# MSG-17: declared before /api/messages/{tx_hash} so the literal wins.
@router.get("/api/messages/search")
async def api_messages_search(
    query: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    _check_offset(offset)
    return await _proxy(
        "messages/search",
        {
            "query": query,
            "q": q,
            "limit": _clamp_limit(limit),
            "offset": offset,
            "cursor": cursor,
            "chain_id": chain_id,
        },
    )


@router.get("/api/messages/reputation/{address}")
async def api_messages_reputation(address: str, chain_id: str | None = None) -> dict[str, Any]:
    return await _proxy(f"reputation/{_check_address(address)}", {"chain_id": chain_id})


@router.get("/api/messages/topics/{slug}/moderation")
async def api_messages_topic_moderation(slug: str, chain_id: str | None = None) -> dict[str, Any]:
    return await _proxy(f"topics/{_check_slug(slug)}/moderation", {"chain_id": chain_id})


@router.get("/api/messages/{tx_hash}/votes")
async def api_messages_votes(tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    return await _proxy(f"messages/{_check_tx_hash(tx_hash)}/votes", {"chain_id": chain_id})


@router.get("/api/messages/{tx_hash}")
async def api_messages_get(tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    return await _proxy(f"messages/{_check_tx_hash(tx_hash)}", {"chain_id": chain_id})
