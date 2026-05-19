"""
Bounty Router - Decentralized task marketplace API

Provides endpoints for:
- Creating bounties
- Listing available bounties
- Claiming bounties
- Submitting solutions
- Verifying and releasing payments
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..services.bounty_service import BountyService, BountyStatus
from ..rate_limiting import rate_limit


router = APIRouter(prefix="/bounty", tags=["bounty"])


class CreateBountyRequest(BaseModel):
    """Request to create a bounty"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    creator: str
    reward: int = Field(..., gt=0)
    deadline: Optional[str] = None
    requirements: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class ClaimBountyRequest(BaseModel):
    """Request to claim a bounty"""
    bounty_id: str
    hunter: str


class SubmitSolutionRequest(BaseModel):
    """Request to submit a solution"""
    bounty_id: str
    hunter: str
    solution_url: str
    notes: Optional[str] = None


class VerifySolutionRequest(BaseModel):
    """Request to verify a solution"""
    bounty_id: str
    verifier: str
    approved: bool
    feedback: Optional[str] = None


# Initialize service
_bounty_service: Optional[BountyService] = None


def get_bounty_service() -> BountyService:
    """Get or create bounty service"""
    global _bounty_service
    if _bounty_service is None:
        _bounty_service = BountyService()
        # Create sample bounties for testing
        _create_sample_bounties()
    return _bounty_service


def _create_sample_bounties():
    """Create sample bounties for testing"""
    service = _bounty_service
    if not service:
        return
    
    # Only create if no bounties exist
    existing = service.list_bounties()
    if existing:
        return
    
    sample_bounties = [
        {
            "title": "Implement Discord Bot Integration",
            "description": "Create a Discord bot that notifies users of new AI job completions",
            "creator": "0x1111111111111111111111111111111111111111",
            "reward": 5000,
            "tags": ["integration", "discord", "bot"],
            "requirements": ["Python 3.9+", "Discord.py", "Webhook support"]
        },
        {
            "title": "Optimize GPU Inference Speed",
            "description": "Improve Ollama inference speed by 20% through model optimization",
            "creator": "0x2222222222222222222222222222222222222222",
            "reward": 10000,
            "tags": ["optimization", "gpu", "performance"],
            "requirements": ["CUDA knowledge", "Model quantization", "Benchmarking"]
        },
        {
            "title": "Write Smart Contract Documentation",
            "description": "Document all staking and governance smart contract functions",
            "creator": "0x3333333333333333333333333333333333333333",
            "reward": 3000,
            "tags": ["documentation", "smart-contracts"],
            "requirements": ["Technical writing", "Solidity understanding"]
        },
        {
            "title": "Create Mobile Wallet App UI",
            "description": "Design and implement React Native UI for AITBC wallet",
            "creator": "0x4444444444444444444444444444444444444444",
            "reward": 8000,
            "tags": ["mobile", "ui", "react-native"],
            "requirements": ["React Native", "TypeScript", "UI/UX design"]
        },
        {
            "title": "Fix Cross-Chain Bridge Edge Cases",
            "description": "Handle reorg scenarios and failed transfers in cross-chain bridge",
            "creator": "0x5555555555555555555555555555555555555555",
            "reward": 15000,
            "tags": ["blockchain", "bridge", "bugfix"],
            "requirements": ["Blockchain expertise", "Error handling", "Testing"]
        }
    ]
    
    for bounty_data in sample_bounties:
        try:
            service.create_bounty(
                title=bounty_data["title"],
                description=bounty_data["description"],
                creator=bounty_data["creator"],
                reward=bounty_data["reward"],
                requirements=bounty_data.get("requirements", []),
                tags=bounty_data.get("tags", [])
            )
        except Exception as e:
            print(f"Failed to create sample bounty: {e}")


@router.post("/create", summary="Create a new bounty")
@rate_limit(rate=10, per=3600)
async def create_bounty(
    request: Request,
    req: CreateBountyRequest
) -> Dict[str, Any]:
    """Create a new bounty task"""
    try:
        service = get_bounty_service()
        
        bounty = service.create_bounty(
            title=req.title,
            description=req.description,
            creator=req.creator,
            reward=req.reward,
            requirements=req.requirements,
            tags=req.tags
        )
        
        return {
            "success": True,
            "bounty": bounty.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create bounty: {str(e)}"
        )


@router.get("/list", summary="List available bounties")
@rate_limit(rate=100, per=60)
async def list_bounties(
    request: Request,
    status: Optional[str] = None,
    tag: Optional[str] = None
) -> Dict[str, Any]:
    """List all bounties with optional filtering"""
    try:
        service = get_bounty_service()
        
        bounties = service.list_bounties(status_filter=status, tag_filter=tag)
        
        return {
            "bounties": [b.to_dict() for b in bounties],
            "count": len(bounties),
            "filters": {
                "status": status,
                "tag": tag
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list bounties: {str(e)}"
        )


@router.get("/{bounty_id}", summary="Get bounty details")
@rate_limit(rate=100, per=60)
async def get_bounty(
    request: Request,
    bounty_id: str
) -> Dict[str, Any]:
    """Get detailed information about a specific bounty"""
    try:
        service = get_bounty_service()
        
        bounty = service.get_bounty(bounty_id)
        if not bounty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bounty {bounty_id} not found"
            )
        
        return bounty.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get bounty: {str(e)}"
        )


@router.post("/claim", summary="Claim a bounty")
@rate_limit(rate=20, per=60)
async def claim_bounty(
    request: Request,
    req: ClaimBountyRequest
) -> Dict[str, Any]:
    """Claim an open bounty for work"""
    try:
        service = get_bounty_service()
        
        success = service.claim_bounty(req.bounty_id, req.hunter)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bounty cannot be claimed"
            )
        
        return {
            "success": True,
            "bounty_id": req.bounty_id,
            "hunter": req.hunter,
            "message": "Bounty claimed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to claim bounty: {str(e)}"
        )


@router.post("/submit", summary="Submit solution")
@rate_limit(rate=20, per=60)
async def submit_solution(
    request: Request,
    req: SubmitSolutionRequest
) -> Dict[str, Any]:
    """Submit a solution for a claimed bounty"""
    try:
        service = get_bounty_service()
        
        success = service.submit_solution(
            req.bounty_id,
            req.hunter,
            req.solution_url,
            req.notes
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Solution cannot be submitted"
            )
        
        return {
            "success": True,
            "bounty_id": req.bounty_id,
            "hunter": req.hunter,
            "solution_url": req.solution_url,
            "message": "Solution submitted for review"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit solution: {str(e)}"
        )


@router.post("/verify", summary="Verify solution")
@rate_limit(rate=20, per=60)
async def verify_solution(
    request: Request,
    req: VerifySolutionRequest
) -> Dict[str, Any]:
    """Verify and approve/reject a submitted solution"""
    try:
        service = get_bounty_service()
        
        success = service.verify_solution(
            req.bounty_id,
            req.verifier,
            req.approved,
            req.feedback
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Solution cannot be verified"
            )
        
        return {
            "success": True,
            "bounty_id": req.bounty_id,
            "approved": req.approved,
            "message": "Solution approved, payment released" if req.approved else "Solution rejected"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify solution: {str(e)}"
        )


@router.get("/stats", summary="Get bounty statistics")
@rate_limit(rate=50, per=60)
async def get_stats(request: Request) -> Dict[str, Any]:
    """Get platform-wide bounty statistics"""
    try:
        service = get_bounty_service()
        
        bounties = service.list_bounties()
        
        total_reward = sum(b.reward for b in bounties)
        open_bounties = len([b for b in bounties if b.status == BountyStatus.OPEN])
        claimed_bounties = len([b for b in bounties if b.status == BountyStatus.CLAIMED])
        completed_bounties = len([b for b in bounties if b.status == BountyStatus.COMPLETED])
        
        return {
            "total_bounties": len(bounties),
            "total_reward_pool": total_reward,
            "open": open_bounties,
            "claimed": claimed_bounties,
            "completed": completed_bounties,
            "completion_rate": completed_bounties / len(bounties) * 100 if bounties else 0
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get("/health", summary="Bounty service health")
async def health_check(request: Request) -> Dict[str, Any]:
    """Check bounty service health"""
    try:
        service = get_bounty_service()
        bounties = service.list_bounties()
        
        return {
            "status": "healthy",
            "total_bounties": len(bounties),
            "service": "bounty"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
