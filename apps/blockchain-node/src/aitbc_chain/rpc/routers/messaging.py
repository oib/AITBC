"""Forum messaging read router — canonical ``/rpc/messaging/*`` paths.

The legacy ``/rpc/contracts/messaging/*`` reads stay mounted from the
contracts router and delegate to the same handlers.
"""

from typing import Any

from fastapi import APIRouter, Request

from ..messaging import (
    messaging_get,
    messaging_messages,
    messaging_search,
    messaging_state,
    messaging_topics,
)

router = APIRouter(prefix="/messaging", tags=["messaging"])


@router.get("/state", summary="Forum index state")
async def state_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    return await messaging_state(request, chain_id=chain_id)  # type: ignore[no-any-return]


@router.get("/topics", summary="List forum topics")
async def topics_route(request: Request, limit: int = 50, offset: int = 0, chain_id: str | None = None) -> dict[str, Any]:
    return await messaging_topics(request, limit=limit, offset=offset, chain_id=chain_id)  # type: ignore[no-any-return]


@router.get("/messages", summary="List forum messages")
async def messages_route(
    request: Request,
    topic: str | None = None,
    author: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    return await messaging_messages(  # type: ignore[no-any-return]
        request, topic=topic, author=author, limit=limit, offset=offset, cursor=cursor, chain_id=chain_id
    )


# Declared before /messages/{tx_hash} so the literal path wins.
@router.get("/messages/search", summary="Search message bodies")
async def search_route(
    request: Request,
    query: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
    chain_id: str | None = None,
) -> dict[str, Any]:
    return await messaging_search(  # type: ignore[no-any-return]
        request, query=query, q=q, limit=limit, offset=offset, cursor=cursor, chain_id=chain_id
    )


@router.get("/messages/{tx_hash}", summary="Get one forum message")
async def message_route(request: Request, tx_hash: str, chain_id: str | None = None) -> dict[str, Any]:
    return await messaging_get(request, tx_hash, chain_id=chain_id)  # type: ignore[no-any-return]
