"""Agent-economy bounty router (V23-42)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger
from ..bounty import deploy_bounty, dispute_bounty, expire_bounty, submit_bounty, verify_bounty

_logger = get_logger(__name__)

router = APIRouter(prefix="/bounty", tags=["agent-economy"])


@router.post("/deploy", summary="Deploy bounty lock")
@rate_limit(rate=20, per=60)
async def deploy_bounty_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Lock bounty reward amount. Operator-signed."""
    return await deploy_bounty(request, body)  # type: ignore[no-any-return]


@router.post("/{bounty_id}/submit", summary="Submit bounty solution")
@rate_limit(rate=20, per=60)
async def submit_bounty_route(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await submit_bounty(request, bounty_id, body)  # type: ignore[no-any-return]


@router.post("/{bounty_id}/verify", summary="Verify bounty submission")
@rate_limit(rate=20, per=60)
async def verify_bounty_route(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await verify_bounty(request, bounty_id, body)  # type: ignore[no-any-return]


@router.post("/{bounty_id}/dispute", summary="Dispute bounty submission")
@rate_limit(rate=20, per=60)
async def dispute_bounty_route(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await dispute_bounty(request, bounty_id, body)  # type: ignore[no-any-return]


@router.post("/{bounty_id}/expire", summary="Expire bounty and refund")
@rate_limit(rate=20, per=60)
async def expire_bounty_route(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await expire_bounty(request, bounty_id, body)  # type: ignore[no-any-return]


__all__ = ["router"]
