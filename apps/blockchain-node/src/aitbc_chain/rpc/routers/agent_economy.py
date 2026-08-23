"""Agent-economy staking router (V23-42)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger
from ..agent_economics_auth import require_int, require_operator_signature
from ..agent_staking import (
    add_to_agent_stake,
    complete_agent_stake,
    create_agent_stake,
    record_claim,
    record_distribute,
    record_performance,
    unbond_agent_stake,
)

_logger = get_logger(__name__)

router = APIRouter(prefix="/agent-staking", tags=["agent-economy"])


@router.post("/stake", summary="Create agent stake")
@rate_limit(rate=20, per=60)
async def create_agent_stake_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Lock an agent stake. Operator-signed."""
    return await create_agent_stake(request, body)  # type: ignore[no-any-return]


@router.post("/stake/{stake_id}/add", summary="Add to agent stake")
@rate_limit(rate=20, per=60)
async def add_to_agent_stake_route(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await add_to_agent_stake(request, stake_id, body)  # type: ignore[no-any-return]


@router.post("/stake/{stake_id}/unbond", summary="Unbond agent stake")
@rate_limit(rate=20, per=60)
async def unbond_agent_stake_route(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await unbond_agent_stake(request, stake_id, body)  # type: ignore[no-any-return]


@router.post("/stake/{stake_id}/complete", summary="Complete agent stake")
@rate_limit(rate=20, per=60)
async def complete_agent_stake_route(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await complete_agent_stake(request, stake_id, body)  # type: ignore[no-any-return]


@router.post("/performance", summary="Record performance update memo")
@rate_limit(rate=20, per=60)
async def record_performance_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    return await record_performance(request, body)  # type: ignore[no-any-return]


@router.post("/agents/{agent_wallet}/distribute", summary="Record earnings distribution memo")
@rate_limit(rate=20, per=60)
async def record_distribute_route(request: Request, agent_wallet: str, body: dict[str, Any]) -> dict[str, Any]:
    return await record_distribute(request, agent_wallet, body)  # type: ignore[no-any-return]


@router.post("/claim-rewards", summary="Record rewards claim memo")
@rate_limit(rate=20, per=60)
async def record_claim_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    return await record_claim(request, body)  # type: ignore[no-any-return]


__all__ = ["router", "require_int", "require_operator_signature"]
