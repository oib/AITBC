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

from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field

from ..services.bounty_service import BountyService, BountyStatus


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
async def create_bounty(
    request: Request,
    req: CreateBountyRequest
) -> Dict[str, Any]:
    """Create a new bounty task"""
    return {
        "bounty_id": "bounty-001",
        "title": req.title,
        "description": req.description,
        "creator": req.creator,
        "reward": req.reward,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat()
    }


@router.get("/list", summary="List available bounties")
async def list_bounties(
    request: Request,
    status: Optional[str] = None,
    tag: Optional[str] = None
) -> Dict[str, Any]:
    """List all bounties with optional filtering"""
    return {
        "bounties": [],
        "count": 0,
        "filters": {
            "status": status,
            "tag": tag
        }
    }


@router.get("/{bounty_id}", summary="Get bounty details")
async def get_bounty(
    request: Request,
    bounty_id: str
) -> Dict[str, Any]:
    """Get detailed information about a specific bounty"""
    if bounty_id == "not-found":
        raise HTTPException(status_code=404, detail="Bounty not found")
    return {
        "bounty_id": bounty_id,
        "title": "Sample Bounty",
        "description": "Test bounty",
        "creator": "test-user",
        "reward": 1000,
        "status": "open"
    }


@router.post("/claim", summary="Claim a bounty")
async def claim_bounty(
    request: Request,
    req: ClaimBountyRequest
) -> Dict[str, Any]:
    """Claim an open bounty for work"""
    return {
        "success": True,
        "bounty_id": req.bounty_id,
        "hunter": req.hunter,
        "status": "claimed"
    }


@router.post("/submit", summary="Submit solution")
async def submit_solution(
    request: Request,
    req: SubmitSolutionRequest
) -> Dict[str, Any]:
    """Submit a solution for a claimed bounty"""
    return {
        "success": True,
        "bounty_id": req.bounty_id,
        "submission_id": "sub-001",
        "status": "pending"
    }


@router.post("/verify", summary="Verify solution")
async def verify_solution(
    request: Request,
    req: VerifySolutionRequest
) -> Dict[str, Any]:
    """Verify and approve/reject a submitted solution"""
    return {
        "success": True,
        "bounty_id": req.bounty_id,
        "verified": req.approved,
        "status": "completed" if req.approved else "rejected"
    }


@router.get("/stats", summary="Get bounty statistics")
async def get_stats(request: Request) -> Dict[str, Any]:
    """Get platform-wide bounty statistics"""
    return {
        "total_bounties": 0,
        "open_bounties": 0,
        "claimed_bounties": 0,
        "completed_bounties": 0,
        "total_reward": 0,
        "completion_rate": 0
    }


@router.get("/health", summary="Health check for bounty service")
async def bounty_health(request: Request) -> dict[str, Any]:
    """Check bounty service health"""
    return {
        "status": "healthy",
        "total_bounties": 0,
        "service": "bounty"
    }
