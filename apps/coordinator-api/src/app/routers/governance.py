"""
Governance Router - Proposal voting and parameter changes
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json

from ..schemas import UserProfile
from ..storage import SessionDep
from ..storage.models_governance import GovernanceProposal, ProposalVote
from sqlmodel import select, func

router = APIRouter(tags=["governance"])


class ProposalCreate(BaseModel):
    """Create a new governance proposal"""
    title: str = Field(..., min_length=10, max_length=200)
    description: str = Field(..., min_length=50, max_length=5000)
    type: str = Field(..., pattern="^(parameter_change|protocol_upgrade|fund_allocation|policy_change)$")
    target: Optional[Dict[str, Any]] = Field(default_factory=dict)
    voting_period: int = Field(default=7, ge=1, le=30)  # days
    quorum_threshold: float = Field(default=0.1, ge=0.01, le=1.0)  # 10% default
    approval_threshold: float = Field(default=0.5, ge=0.01, le=1.0)  # 50% default


class ProposalResponse(BaseModel):
    """Governance proposal response"""
    id: str
    title: str
    description: str
    type: str
    target: Dict[str, Any]
    proposer: str
    status: str
    created_at: datetime
    voting_deadline: datetime
    quorum_threshold: float
    approval_threshold: float
    current_quorum: float
    current_approval: float
    votes_for: int
    votes_against: int
    votes_abstain: int
    total_voting_power: int


class VoteSubmit(BaseModel):
    """Submit a vote on a proposal"""
    proposal_id: str
    vote: str = Field(..., pattern="^(for|against|abstain)$")
    reason: Optional[str] = Field(max_length=500)


@router.post("/governance/proposals", response_model=ProposalResponse)
async def create_proposal(
    proposal: ProposalCreate,
    user: UserProfile,
    session: SessionDep
) -> ProposalResponse:
    """Create a new governance proposal"""
    
    # Check if user has voting power
    voting_power = await get_user_voting_power(user.user_id, session)
    if voting_power == 0:
        raise HTTPException(403, "You must have voting power to create proposals")
    
    # Create proposal
    db_proposal = GovernanceProposal(
        title=proposal.title,
        description=proposal.description,
        type=proposal.type,
        target=proposal.target,
        proposer=user.user_id,
        status="active",
        created_at=datetime.utcnow(),
        voting_deadline=datetime.utcnow() + timedelta(days=proposal.voting_period),
        quorum_threshold=proposal.quorum_threshold,
        approval_threshold=proposal.approval_threshold
    )
    
    session.add(db_proposal)
    session.commit()
    session.refresh(db_proposal)
    
    # Return response
    return await format_proposal_response(db_proposal, session)


@router.get("/governance/proposals", response_model=List[ProposalResponse])
async def list_proposals(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    session: SessionDep = None
) -> List[ProposalResponse]:
    """List governance proposals"""
    
    query = select(GovernanceProposal)
    
    if status:
        query = query.where(GovernanceProposal.status == status)
    
    query = query.order_by(GovernanceProposal.created_at.desc())
    query = query.offset(offset).limit(limit)
    
    proposals = session.exec(query).all()
    
    responses = []
    for proposal in proposals:
        formatted = await format_proposal_response(proposal, session)
        responses.append(formatted)
    
    return responses


@router.get("/governance/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: str,
    session: SessionDep
) -> ProposalResponse:
    """Get a specific proposal"""
    
    proposal = session.get(GovernanceProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    
    return await format_proposal_response(proposal, session)


@router.post("/governance/vote")
async def submit_vote(
    vote: VoteSubmit,
    user: UserProfile,
    session: SessionDep
) -> Dict[str, str]:
    """Submit a vote on a proposal"""
    
    # Check proposal exists and is active
    proposal = session.get(GovernanceProposal, vote.proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    
    if proposal.status != "active":
        raise HTTPException(400, "Proposal is not active for voting")
    
    if datetime.utcnow() > proposal.voting_deadline:
        raise HTTPException(400, "Voting period has ended")
    
    # Check user voting power
    voting_power = await get_user_voting_power(user.user_id, session)
    if voting_power == 0:
        raise HTTPException(403, "You have no voting power")
    
    # Check if already voted
    existing = session.exec(
        select(ProposalVote).where(
            ProposalVote.proposal_id == vote.proposal_id,
            ProposalVote.voter_id == user.user_id
        )
    ).first()
    
    if existing:
        # Update existing vote
        existing.vote = vote.vote
        existing.reason = vote.reason
        existing.voted_at = datetime.utcnow()
    else:
        # Create new vote
        db_vote = ProposalVote(
            proposal_id=vote.proposal_id,
            voter_id=user.user_id,
            vote=vote.vote,
            voting_power=voting_power,
            reason=vote.reason,
            voted_at=datetime.utcnow()
        )
        session.add(db_vote)
    
    session.commit()
    
    # Check if proposal should be finalized
    if datetime.utcnow() >= proposal.voting_deadline:
        await finalize_proposal(proposal, session)
    
    return {"message": "Vote submitted successfully"}


@router.get("/governance/voting-power/{user_id}")
async def get_voting_power(
    user_id: str,
    session: SessionDep
) -> Dict[str, int]:
    """Get a user's voting power"""
    
    power = await get_user_voting_power(user_id, session)
    return {"user_id": user_id, "voting_power": power}


@router.get("/governance/parameters")
async def get_governance_parameters(
    session: SessionDep
) -> Dict[str, Any]:
    """Get current governance parameters"""
    
    # These would typically be stored in a config table
    return {
        "min_proposal_voting_power": 1000,
        "max_proposal_title_length": 200,
        "max_proposal_description_length": 5000,
        "default_voting_period_days": 7,
        "max_voting_period_days": 30,
        "min_quorum_threshold": 0.01,
        "max_quorum_threshold": 1.0,
        "min_approval_threshold": 0.01,
        "max_approval_threshold": 1.0,
        "execution_delay_hours": 24
    }


@router.post("/governance/execute/{proposal_id}")
async def execute_proposal(
    proposal_id: str,
    background_tasks: BackgroundTasks,
    session: SessionDep
) -> Dict[str, str]:
    """Execute an approved proposal"""
    
    proposal = session.get(GovernanceProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    
    if proposal.status != "passed":
        raise HTTPException(400, "Proposal must be passed to execute")
    
    if datetime.utcnow() < proposal.voting_deadline + timedelta(hours=24):
        raise HTTPException(400, "Must wait 24 hours after voting ends to execute")
    
    # Execute proposal based on type
    if proposal.type == "parameter_change":
        await execute_parameter_change(proposal.target, background_tasks)
    elif proposal.type == "protocol_upgrade":
        await execute_protocol_upgrade(proposal.target, background_tasks)
    elif proposal.type == "fund_allocation":
        await execute_fund_allocation(proposal.target, background_tasks)
    elif proposal.type == "policy_change":
        await execute_policy_change(proposal.target, background_tasks)
    
    # Update proposal status
    proposal.status = "executed"
    proposal.executed_at = datetime.utcnow()
    session.commit()
    
    return {"message": "Proposal executed successfully"}


# Helper functions

async def get_user_voting_power(user_id: str, session) -> int:
    """Calculate a user's voting power based on AITBC holdings"""
    
    # In a real implementation, this would query the blockchain
    # For now, return a mock value
    return 10000  # Mock voting power


async def format_proposal_response(proposal: GovernanceProposal, session) -> ProposalResponse:
    """Format a proposal for API response"""
    
    # Get vote counts
    votes = session.exec(
        select(ProposalVote).where(ProposalVote.proposal_id == proposal.id)
    ).all()
    
    votes_for = sum(1 for v in votes if v.vote == "for")
    votes_against = sum(1 for v in votes if v.vote == "against")
    votes_abstain = sum(1 for v in votes if v.vote == "abstain")
    
    # Get total voting power
    total_power = sum(v.voting_power for v in votes)
    power_for = sum(v.voting_power for v in votes if v.vote == "for")
    
    # Calculate quorum and approval
    total_voting_power = await get_total_voting_power(session)
    current_quorum = total_power / total_voting_power if total_voting_power > 0 else 0
    current_approval = power_for / total_power if total_power > 0 else 0
    
    return ProposalResponse(
        id=proposal.id,
        title=proposal.title,
        description=proposal.description,
        type=proposal.type,
        target=proposal.target,
        proposer=proposal.proposer,
        status=proposal.status,
        created_at=proposal.created_at,
        voting_deadline=proposal.voting_deadline,
        quorum_threshold=proposal.quorum_threshold,
        approval_threshold=proposal.approval_threshold,
        current_quorum=current_quorum,
        current_approval=current_approval,
        votes_for=votes_for,
        votes_against=votes_against,
        votes_abstain=votes_abstain,
        total_voting_power=total_voting_power
    )


async def get_total_voting_power(session) -> int:
    """Get total voting power in the system"""
    
    # In a real implementation, this would sum all AITBC tokens
    return 1000000  # Mock total voting power


async def finalize_proposal(proposal: GovernanceProposal, session):
    """Finalize a proposal after voting ends"""
    
    # Get final vote counts
    votes = session.exec(
        select(ProposalVote).where(ProposalVote.proposal_id == proposal.id)
    ).all()
    
    total_power = sum(v.voting_power for v in votes)
    power_for = sum(v.voting_power for v in votes if v.vote == "for")
    
    total_voting_power = await get_total_voting_power(session)
    quorum = total_power / total_voting_power if total_voting_power > 0 else 0
    approval = power_for / total_power if total_power > 0 else 0
    
    # Check if quorum met
    if quorum < proposal.quorum_threshold:
        proposal.status = "rejected"
        proposal.rejection_reason = "Quorum not met"
    # Check if approval threshold met
    elif approval < proposal.approval_threshold:
        proposal.status = "rejected"
        proposal.rejection_reason = "Approval threshold not met"
    else:
        proposal.status = "passed"
    
    session.commit()


async def execute_parameter_change(target: Dict[str, Any], background_tasks):
    """Execute a parameter change proposal"""
    
    # This would update system parameters
    print(f"Executing parameter change: {target}")
    # Implementation would depend on the specific parameters


async def execute_protocol_upgrade(target: Dict[str, Any], background_tasks):
    """Execute a protocol upgrade proposal"""
    
    # This would trigger a protocol upgrade
    print(f"Executing protocol upgrade: {target}")
    # Implementation would involve coordinating with nodes


async def execute_fund_allocation(target: Dict[str, Any], background_tasks):
    """Execute a fund allocation proposal"""
    
    # This would transfer funds from treasury
    print(f"Executing fund allocation: {target}")
    # Implementation would involve treasury management


async def execute_policy_change(target: Dict[str, Any], background_tasks):
    """Execute a policy change proposal"""
    
    # This would update system policies
    print(f"Executing policy change: {target}")
    # Implementation would depend on the specific policy


# Export the router
__all__ = ["router"]
