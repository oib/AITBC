"""
Governance Router - On-chain governance API endpoints

Provides:
- Proposal creation
- Voting
- Proposal execution
- Governance parameters
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..services.governance_service import get_governance_service
from aitbc.rate_limiting import rate_limit


router = APIRouter(prefix="/governance", tags=["governance"])


class CreateProposalRequest(BaseModel):
    """Request to create a proposal"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    proposer: str
    proposal_type: str = "parameter_change"
    call_data: Optional[Dict[str, Any]] = None


class CastVoteRequest(BaseModel):
    """Request to cast a vote"""
    proposal_id: str
    voter: str
    choice: str = Field(..., pattern="^(for|against|abstain)$")
    voting_power: int = Field(..., gt=0)


class ExecuteProposalRequest(BaseModel):
    """Request to execute a proposal"""
    proposal_id: str
    executor: str


@router.post("/proposals", summary="Create governance proposal")
@rate_limit(rate=5, per=3600)
async def create_proposal(
    request: Request,
    req: CreateProposalRequest
) -> Dict[str, Any]:
    """
    Create a new governance proposal.
    
    Requires minimum stake to create proposals.
    """
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        # Verify proposer has minimum stake
        proposer_power = service.get_voting_power(req.proposer)
        if proposer_power < service.MIN_PROPOSAL_STAKE:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stake: {proposer_power} < {service.MIN_PROPOSAL_STAKE}"
            )
        
        proposal = service.create_proposal(
            title=req.title,
            description=req.description,
            proposer=req.proposer,
            proposal_type=req.proposal_type,
            call_data=req.call_data
        )
        
        return {
            "success": True,
            **proposal.to_dict()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create proposal: {str(e)}")


@router.post("/vote", summary="Cast vote on proposal")
@rate_limit(rate=20, per=60)
async def cast_vote(
    request: Request,
    req: CastVoteRequest
) -> Dict[str, Any]:
    """Cast a vote on an active proposal"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        # Verify voting power matches
        actual_power = service.get_voting_power(req.voter)
        if req.voting_power > actual_power:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient voting power: {actual_power} < {req.voting_power}"
            )
        
        success = service.cast_vote(
            proposal_id=req.proposal_id,
            voter=req.voter,
            choice=req.choice,
            voting_power=req.voting_power
        )
        
        return {
            "success": success,
            "proposal_id": req.proposal_id,
            "voter": req.voter,
            "choice": req.choice,
            "power": req.voting_power
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cast vote: {str(e)}")


@router.post("/execute", summary="Execute passed proposal")
@rate_limit(rate=10, per=60)
async def execute_proposal(
    request: Request,
    req: ExecuteProposalRequest
) -> Dict[str, Any]:
    """Execute a proposal that has passed voting"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        success = service.execute_proposal(req.proposal_id, req.executor)
        
        return {
            "success": success,
            "proposal_id": req.proposal_id,
            "executor": req.executor,
            "executed_at": __import__('datetime').datetime.now(
                __import__('datetime').timezone.utc
            ).isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.get("/proposals/{proposal_id}", summary="Get proposal details")
@rate_limit(rate=100, per=60)
async def get_proposal(
    request: Request,
    proposal_id: str
) -> Dict[str, Any]:
    """Get detailed information about a specific proposal"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        proposal = service.get_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
        
        return proposal.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get proposal: {str(e)}")


@router.get("/proposals", summary="List proposals")
@rate_limit(rate=50, per=60)
async def list_proposals(
    request: Request,
    status: Optional[str] = None,
    proposer: Optional[str] = None
) -> Dict[str, Any]:
    """List governance proposals with optional filters"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        proposals = service.list_proposals(status=status, proposer=proposer)
        
        return {
            "proposals": [p.to_dict() for p in proposals],
            "count": len(proposals),
            "filters": {
                "status": status,
                "proposer": proposer
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list proposals: {str(e)}")


@router.get("/proposals/{proposal_id}/votes", summary="Get proposal votes")
@rate_limit(rate=50, per=60)
async def get_votes(
    request: Request,
    proposal_id: str
) -> Dict[str, Any]:
    """Get all votes cast on a proposal"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        votes = service.get_votes(proposal_id)
        
        return {
            "proposal_id": proposal_id,
            "votes": [
                {
                    "voter": v.voter,
                    "choice": v.choice,
                    "power": v.power,
                    "timestamp": v.timestamp.isoformat()
                }
                for v in votes
            ],
            "count": len(votes)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get votes: {str(e)}")


@router.get("/params", summary="Get governance parameters")
@rate_limit(rate=100, per=60)
async def get_params(request: Request) -> Dict[str, Any]:
    """Get current governance system parameters"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        return service.get_governance_params()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get params: {str(e)}")


@router.get("/voting-power/{address}", summary="Get voting power")
@rate_limit(rate=100, per=60)
async def get_voting_power(
    request: Request,
    address: str
) -> Dict[str, Any]:
    """Get stake-weighted voting power for an address"""
    try:
        service = get_governance_service()
        if not service:
            raise HTTPException(status_code=503, detail="Governance service not initialized")
        
        power = service.get_voting_power(address)
        
        return {
            "address": address,
            "voting_power": power,
            "can_create_proposal": power >= service.MIN_PROPOSAL_STAKE
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get voting power: {str(e)}")


@router.get("/health", summary="Governance health check")
async def health_check(request: Request) -> Dict[str, Any]:
    """Check governance service health"""
    try:
        service = get_governance_service()
        if not service:
            return {"status": "unhealthy", "error": "Service not initialized"}
        
        params = service.get_governance_params()
        
        return {
            "status": "healthy",
            "total_proposals": params["total_proposals"],
            "active_proposals": params["active_proposals"]
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
