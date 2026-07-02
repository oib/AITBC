"""
Staking, identity, and governance router.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(tags=["staking", "identity", "governance"])

# Optional imports - will be None if module not available
cast_governance_vote = None
create_governance_proposal = None
get_agent_identity = None
get_governance_proposal = None
get_staking_info = None
register_agent_identity = None
stake_tokens = None
unstake_tokens = None
verify_agent_identity = None

try:
    from ..staking import (
        cast_governance_vote,
        create_governance_proposal,
        get_agent_identity,
        get_governance_proposal,
        get_staking_info,
        register_agent_identity,
        stake_tokens,
        unstake_tokens,
        verify_agent_identity,
    )
except ImportError as e:
    _logger.error("Staking module not available: %s — affected endpoints will return 503", e)


@router.post("/staking/stake", summary="Stake tokens")
@rate_limit(rate=20, per=60)
async def stake_tokens_route(request: Request, stake_data: dict) -> dict[str, Any]:
    """Stake tokens for consensus participation"""
    if stake_tokens is None:
        raise HTTPException(status_code=503, detail="Staking module not available")
    return await stake_tokens(request, stake_data)


@router.post("/staking/unstake", summary="Unstake tokens")
@rate_limit(rate=10, per=60)
async def unstake_tokens_route(request: Request, unstake_data: dict) -> dict[str, Any]:
    """Unstake tokens after lock period expires"""
    if unstake_tokens is None:
        raise HTTPException(status_code=503, detail="Staking module not available")
    return await unstake_tokens(request, unstake_data)


@router.get("/staking/{address}", summary="Get staking info")
@rate_limit(rate=100, per=60)
async def get_staking_info_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get staking information for an address"""
    if get_staking_info is None:
        raise HTTPException(status_code=503, detail="Staking module not available")
    return await get_staking_info(request, address, chain_id)


@router.post("/identity/register", summary="Register agent identity")
@rate_limit(rate=20, per=60)
async def register_agent_identity_route(request: Request, identity_data: dict) -> dict[str, Any]:
    """Register an agent identity on the blockchain"""
    if register_agent_identity is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return await register_agent_identity(request, identity_data)


@router.get("/identity/{agent_id}", summary="Get agent identity")
@rate_limit(rate=50, per=60)
async def get_agent_identity_route(request: Request, agent_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get agent identity from blockchain"""
    if get_agent_identity is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return await get_agent_identity(request, agent_id, chain_id)


@router.post("/identity/verify", summary="Verify agent identity")
@rate_limit(rate=50, per=60)
async def verify_agent_identity_route(request: Request, verification_data: dict) -> dict[str, Any]:
    """Verify an agent identity on the blockchain"""
    if verify_agent_identity is None:
        raise HTTPException(status_code=503, detail="Identity module not available")
    return await verify_agent_identity(request, verification_data)


@router.post("/governance/proposal", summary="Create governance proposal")
@rate_limit(rate=20, per=60)
async def create_governance_proposal_route(request: Request, proposal_data: dict) -> dict[str, Any]:
    """Create a governance proposal on the blockchain"""
    if create_governance_proposal is None:
        raise HTTPException(status_code=503, detail="Governance module not available")
    return await create_governance_proposal(request, proposal_data)


@router.post("/governance/vote", summary="Cast governance vote")
@rate_limit(rate=50, per=60)
async def cast_governance_vote_route(request: Request, vote_data: dict) -> dict[str, Any]:
    """Cast a vote on a governance proposal"""
    if cast_governance_vote is None:
        raise HTTPException(status_code=503, detail="Governance module not available")
    return await cast_governance_vote(request, vote_data)


@router.get("/governance/proposal/{proposal_id}", summary="Get governance proposal")
@rate_limit(rate=50, per=60)
async def get_governance_proposal_route(request: Request, proposal_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get a governance proposal from the blockchain"""
    if get_governance_proposal is None:
        raise HTTPException(status_code=503, detail="Governance module not available")
    return await get_governance_proposal(request, proposal_id, chain_id)
