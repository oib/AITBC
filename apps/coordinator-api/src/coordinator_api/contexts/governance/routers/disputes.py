"""
Disputes Router - Dispute resolution API endpoints

Provides:
- Dispute filing
- Evidence submission
- Arbitrator voting
- Case tracking
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ....auth import AuthDep
from pydantic import BaseModel

from ..services.dispute_resolution import get_dispute_service

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
def file_dispute(request: Request, req: FileDisputeRequest, user: AuthDep) -> dict[str, Any]:
    """File a new dispute for a job"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # The filer is the authenticated caller — never a body field (#1333/#1334).
        filed_by = user["sub"]

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
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/evidence", summary="Submit evidence")
def submit_evidence(request: Request, req: SubmitEvidenceRequest, user: AuthDep) -> dict[str, Any]:
    """Submit evidence for a dispute"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # The submitter is the authenticated caller — the service still
        # enforces membership in {client, provider} (#1333).
        submitted_by = user["sub"]

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
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/vote", summary="Cast arbitrator vote")
def cast_vote(request: Request, req: CastVoteRequest, user: AuthDep) -> dict[str, Any]:
    """Cast a vote as an arbitrator"""
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        # The arbitrator is the authenticated caller — never a constant
        # (#1334). One vote per arbitrator now actually binds per identity.
        arbitrator = user["sub"]

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
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/health", summary="Health check")
def disputes_health(request: Request) -> dict[str, Any]:
    """Check disputes service health"""
    return {"status": "healthy", "active_disputes": 0, "service": "disputes"}


@router.get("/{dispute_id}", summary="Get dispute details")
def get_dispute(request: Request, dispute_id: str) -> dict[str, Any]:
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
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/", summary="List disputes")
def list_disputes(request: Request, status: str | None = None, party: str | None = None) -> dict[str, Any]:
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
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/arbitrators/register", summary="Register as arbitrator")
def register_arbitrator(request: Request, address: str, user: AuthDep) -> dict[str, Any]:
    """Register an address as an arbitrator.

    Callers may only register their own authenticated identity — the
    ``address`` parameter is retained for compatibility and must match
    the caller's subject (#1335). Staking requirements remain a
    documented TODO.
    """
    try:
        service = get_dispute_service()
        if not service:
            raise HTTPException(status_code=503, detail="Dispute service not initialized")

        if address != user["sub"]:
            raise HTTPException(status_code=403, detail="Can only register your own identity as arbitrator")
        success = service.register_arbitrator(user["sub"])

        return {"success": success, "address": address, "message": "Arbitrator registered"}

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
