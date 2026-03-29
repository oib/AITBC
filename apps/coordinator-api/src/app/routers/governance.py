from sqlalchemy.orm import Session
from typing import Annotated
"""
Decentralized Governance API Endpoints
REST API for OpenClaw DAO voting, proposals, and governance analytics
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field
import logging
logger = logging.getLogger(__name__)

from ..storage import get_session
from ..services.governance_service import GovernanceService
from ..domain.governance import (
    GovernanceProfile, Proposal, Vote, DaoTreasury, TransparencyReport,
    ProposalStatus, VoteType, GovernanceRole
)



router = APIRouter(prefix="/governance", tags=["governance"])

# Models
class ProfileInitRequest(BaseModel):
    user_id: str
    initial_voting_power: float = 0.0

class DelegationRequest(BaseModel):
    delegatee_id: str

class ProposalCreateRequest(BaseModel):
    title: str
    description: str
    category: str = "general"
    execution_payload: Dict[str, Any] = Field(default_factory=dict)
    quorum_required: float = 1000.0
    voting_starts: Optional[str] = None
    voting_ends: Optional[str] = None

class VoteRequest(BaseModel):
    vote_type: VoteType
    reason: Optional[str] = None

# Endpoints - Profile & Delegation
@router.post("/profiles", response_model=GovernanceProfile)
async def init_governance_profile(request: ProfileInitRequest, session: Annotated[Session, Depends(get_session)]):
    """Initialize a governance profile for a user"""
    service = GovernanceService(session)
    try:
        profile = await service.get_or_create_profile(request.user_id, request.initial_voting_power)
        return profile
    except Exception as e:
        logger.error(f"Error creating governance profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/profiles/{profile_id}/delegate", response_model=GovernanceProfile)
async def delegate_voting_power(profile_id: str, request: DelegationRequest, session: Annotated[Session, Depends(get_session)]):
    """Delegate your voting power to another DAO member"""
    service = GovernanceService(session)
    try:
        profile = await service.delegate_votes(profile_id, request.delegatee_id)
        return profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints - Proposals
@router.post("/proposals", response_model=Proposal)
async def create_proposal(
    session: Annotated[Session, Depends(get_session)],
    proposer_id: str = Query(...),
    request: ProposalCreateRequest = Body(...)
):
    """Submit a new governance proposal to the DAO"""
    service = GovernanceService(session)
    try:
        proposal = await service.create_proposal(proposer_id, request.dict())
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proposals/{proposal_id}/vote", response_model=Vote)
async def cast_vote(
    proposal_id: str,
    session: Annotated[Session, Depends(get_session)],
    voter_id: str = Query(...),
    request: VoteRequest = Body(...)
):
    """Cast a vote on an active proposal"""
    service = GovernanceService(session)
    try:
        vote = await service.cast_vote(
            proposal_id=proposal_id,
            voter_id=voter_id,
            vote_type=request.vote_type,
            reason=request.reason
        )
        return vote
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proposals/{proposal_id}/process", response_model=Proposal)
async def process_proposal(proposal_id: str, session: Annotated[Session, Depends(get_session)]):
    """Manually trigger the lifecycle check of a proposal (e.g., tally votes when time ends)"""
    service = GovernanceService(session)
    try:
        proposal = await service.process_proposal_lifecycle(proposal_id)
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proposals/{proposal_id}/execute", response_model=Proposal)
async def execute_proposal(
    proposal_id: str,
    session: Annotated[Session, Depends(get_session)],
    executor_id: str = Query(...)
):
    """Execute the payload of a succeeded proposal"""
    service = GovernanceService(session)
    try:
        proposal = await service.execute_proposal(proposal_id, executor_id)
        return proposal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints - Analytics
@router.post("/analytics/reports", response_model=TransparencyReport)
async def generate_transparency_report(
    session: Annotated[Session, Depends(get_session)],
    period: str = Query(..., description="e.g., 2026-Q1")
):
    """Generate a governance analytics and transparency report"""
    service = GovernanceService(session)
    try:
        report = await service.generate_transparency_report(period)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
