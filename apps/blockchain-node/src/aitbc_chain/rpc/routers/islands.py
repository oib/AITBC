"""
Islands router.
"""

from typing import Any
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/islands", tags=["islands"])

# Optional imports - will be None if module not available
join_island: Callable[..., Any] | None = None
leave_island: Callable[..., Any] | None = None
list_islands: Callable[..., Any] | None = None
get_island: Callable[..., Any] | None = None
request_bridge: Callable[..., Any] | None = None
JoinIslandRequest: Any = None
JoinIslandResponse: Any = None
LeaveIslandRequest: Any = None
LeaveIslandResponse: Any = None
BridgeRequestRequest: Any = None
BridgeRequestResponse: Any = None

try:
    from ..islands import (
        BridgeRequestRequest,
        BridgeRequestResponse,
        JoinIslandRequest,
        JoinIslandResponse,
        LeaveIslandRequest,
        LeaveIslandResponse,
        get_island,
        join_island,
        leave_island,
        list_islands,
        request_bridge,
    )
except ImportError as e:
    _logger.error("Islands module not available: %s — affected endpoints will return 503", e)


@router.post("/join", summary="Join an island")
async def join_island_route(request: JoinIslandRequest) -> JoinIslandResponse:
    """Join an island for edge compute operations"""
    if join_island is None:
        raise HTTPException(status_code=503, detail="Islands module not available")
    return await join_island(request)


@router.post("/leave", summary="Leave an island")
async def leave_island_route(request: LeaveIslandRequest) -> LeaveIslandResponse:
    """Leave an island"""
    if leave_island is None:
        raise HTTPException(status_code=503, detail="Islands module not available")
    return await leave_island(request)


@router.get("", summary="List all islands")
@rate_limit(rate=100, per=60)
async def list_islands_route() -> dict[str, Any]:
    """List all islands that the node is a member of"""
    if list_islands is None:
        raise HTTPException(status_code=503, detail="Islands module not available")
    return await list_islands()  # type: ignore[no-any-return]


@router.get("/{island_id}", summary="Get island details")
@rate_limit(rate=100, per=60)
async def get_island_route(island_id: str) -> dict[str, Any]:
    """Get details of a specific island"""
    if get_island is None:
        raise HTTPException(status_code=503, detail="Islands module not available")
    return await get_island(island_id)  # type: ignore[no-any-return]


@router.post("/bridge", summary="Request a bridge to another island")
async def request_bridge_route(request: BridgeRequestRequest) -> BridgeRequestResponse:
    """Request a bridge to another island for cross-island communication"""
    if request_bridge is None:
        raise HTTPException(status_code=503, detail="Islands module not available")
    return await request_bridge(request)
