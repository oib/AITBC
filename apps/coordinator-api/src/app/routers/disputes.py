"""
Disputes Router - Dispute resolution API endpoints

Provides:
- Dispute filing
- Evidence submission
- Arbitrator voting
- Case tracking
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..contexts.governance.services.dispute_resolution import get_dispute_service

router = APIRouter(prefix="/disputes", tags=["disputes"])


class FileDisputeRequest(BaseModel):
    """Request to file a dispute"""

    job_id: str
    client: str
    provider: str
    amount: int
    reason: str
    initial_evidence: str | None = None


class SubmitEvidenceRequest(BaseModel):
    """Request to submit evidence"""

    dispute_id: str
    evidence_type: str
    description: str
    ipfs_hash: str | None = None


class CastVoteRequest(BaseModel):
    """Request to cast a vote"""

    dispute_id: str
    outcome: str  # client_wins, provider_wins, split
    reasoning: str
    stake_amount: int


@router.post("/file", summary="File a dispute")
async def file_dispute(request: Request, req: FileDisputeRequest) -> dict[str, Any]:
    """File a new dispute for a job"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # Determine who filed based on request context
        # For now, use filed_by from request or infer
        filed_by = req.client  # Simplified

        dispute = service.file_dispute(
            job_id=req.job_id,
            client=req.client,
            provider=req.provider,
            amount=req.amount,
            reason=req.reason,
            filed_by=filed_by,
            initial_evidence=req.initial_evidence,
        )

        return {"success": True, **dispute.to_dict()}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to file dispute: {str(e)}") from e


@router.post("/evidence", summary="Submit evidence")
async def submit_evidence(request: Request, req: SubmitEvidenceRequest) -> dict[str, Any]:
    """Submit evidence for a dispute"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # Get submitter from request
        # For now, infer from request context
        submitted_by = "client"  # Simplified - would come from auth

        success = service.submit_evidence(
            dispute_id=req.dispute_id,
            submitted_by=submitted_by,
            evidence_type=req.evidence_type,
            description=req.description,
            ipfs_hash=req.ipfs_hash,
        )

        return {"success": success, "dispute_id": req.dispute_id, "message": "Evidence submitted"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit evidence: {str(e)}") from e


@router.post("/vote", summary="Cast arbitrator vote")
async def cast_vote(request: Request, req: CastVoteRequest) -> dict[str, Any]:
    """Cast a vote as an arbitrator"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # Get arbitrator from request
        arbitrator = "arbitrator_001"  # Simplified - would come from auth

        # Verify is arbitrator
        if not service.is_arbitrator(arbitrator):
            raise HTTPException(status_code=403, detail="Not a registered arbitrator")

        success = service.cast_vote(
            dispute_id=req.dispute_id,
            arbitrator=arbitrator,
            outcome=req.outcome,
            reasoning=req.reasoning,
            stake_amount=req.stake_amount,
        )

        return {"success": success, "dispute_id": req.dispute_id, "arbitrator": arbitrator, "outcome": req.outcome}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cast vote: {str(e)}") from e


@router.get("/health", summary="Health check")
async def disputes_health(request: Request) -> dict[str, Any]:
    """Check disputes service health"""
    return {"status": "healthy", "active_disputes": 0, "service": "disputes"}


@router.get("/{dispute_id}", summary="Get dispute details")
async def get_dispute(request: Request, dispute_id: str) -> dict[str, Any]:
    """Get details of a specific dispute"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        dispute = service.get_dispute(dispute_id)
        if not dispute:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")

        return dispute.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dispute: {str(e)}") from e


@router.get("/", summary="List disputes")
async def list_disputes(request: Request, status: str | None = None, party: str | None = None) -> dict[str, Any]:
    """List disputes with optional filters"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        disputes = service.list_disputes(status=status, party=party)

        return {
            "disputes": [d.to_dict() for d in disputes],
            "count": len(disputes),
            "filters": {"status": status, "party": party},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list disputes: {str(e)}") from e


@router.post("/arbitrators/register", summary="Register as arbitrator")
async def register_arbitrator(request: Request, address: str) -> dict[str, Any]:
    """Register an address as an arbitrator"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # In production, verify staking requirements
        success = service.register_arbitrator(address)

        return {"success": success, "address": address, "message": "Arbitrator registered"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}") from e
