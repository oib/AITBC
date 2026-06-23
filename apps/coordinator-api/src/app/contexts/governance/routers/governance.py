"""
Decentralized Governance API Endpoints
REST API for agent DAO voting, proposals, and governance analytics
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ....domain.governance import GovernanceProfile, Proposal, TransparencyReport, Vote, VoteType
from ....storage import get_session
from ..services.governance_service import GovernanceService

logger = get_logger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])


class ProfileInitRequest(BaseModel):
    user_id: str
    initial_voting_power: float = 0.0


class DelegationRequest(BaseModel):
    delegatee_id: str


class ProposalCreateRequest(BaseModel):
    title: str
    description: str
    category: str = "general"
    execution_payload: dict[str, Any] = Field(default_factory=dict)
    quorum_required: float = 1000.0
    voting_starts: str | None = None
    voting_ends: str | None = None


class VoteRequest(BaseModel):
    vote_type: VoteType
    reason: str | None = None


@router.post("/profiles", response_model=GovernanceProfile)
@rate_limit(rate=20, per=60)
async def init_governance_profile(
    request: Request, profile_request: ProfileInitRequest, session: Annotated[Session, Depends(get_session)]
) -> GovernanceProfile:
    """Initialize a governance profile for a user"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        profile = await service.get_or_create_profile(request.user_id, request.initial_voting_power)  # type: ignore[attr-defined]
        return profile
    except Exception as e:
        logger.error("Error creating governance profile: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/profiles/{profile_id}/delegate", response_model=GovernanceProfile)
@rate_limit(rate=20, per=60)
async def delegate_voting_power(
    request: Request, profile_id: str, delegation_request: DelegationRequest, session: Annotated[Session, Depends(get_session)]
) -> GovernanceProfile:
    """Delegate your voting power to another DAO member"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        profile = await service.delegate_votes(profile_id, request.delegatee_id)  # type: ignore[attr-defined]
        return profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/proposals", response_model=Proposal)
@rate_limit(rate=20, per=60)
async def create_proposal(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    proposer_id: Annotated[str, Query(...)],
    proposal_request: Annotated[ProposalCreateRequest, Body(...)],
) -> Proposal:
    """Submit a new governance proposal to the DAO"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        proposal = await service.create_proposal(proposer_id, proposal_request.dict())
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/proposals/{proposal_id}/vote", response_model=Vote)
@rate_limit(rate=20, per=60)
async def cast_vote(
    request: Request,
    proposal_id: str,
    session: Annotated[Session, Depends(get_session)],
    voter_id: Annotated[str, Query(...)],
    vote_request: Annotated[VoteRequest, Body(...)],
) -> Vote:
    """Cast a vote on an active proposal"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        vote = await service.cast_vote(
            proposal_id=proposal_id, voter_id=voter_id, vote_type=vote_request.vote_type, reason=vote_request.reason
        )
        return vote
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/proposals/{proposal_id}/process", response_model=Proposal)
@rate_limit(rate=20, per=60)
async def process_proposal(request: Request, proposal_id: str, session: Annotated[Session, Depends(get_session)]) -> Proposal:
    """Manually trigger the lifecycle check of a proposal (e.g., tally votes when time ends)"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        proposal = await service.process_proposal_lifecycle(proposal_id)
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/proposals/{proposal_id}/execute", response_model=Proposal)
@rate_limit(rate=20, per=60)
async def execute_proposal(
    request: Request,
    proposal_id: str,
    session: Annotated[Session, Depends(get_session)],
    executor_id: Annotated[str, Query(...)],
) -> Proposal:
    """Execute the payload of a succeeded proposal"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        proposal = await service.execute_proposal(proposal_id, executor_id)
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/analytics/reports", response_model=TransparencyReport)
@rate_limit(rate=200, per=60)
async def generate_transparency_report(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    period: Annotated[str, Query(..., description="e.g., 2026-Q1")],
) -> TransparencyReport:
    """Generate a governance analytics and transparency report"""
    service = GovernanceService(session)  # type: ignore[arg-type]
    try:
        report = await service.generate_transparency_report(period)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
