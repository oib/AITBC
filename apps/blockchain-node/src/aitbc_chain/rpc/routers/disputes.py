"""
Dispute resolution router.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials


from ...logger import get_logger
from ...models.dispute import (
    AuthorizeArbitratorRequest,
    AuthorizeArbitratorResponse,
    FileDisputeRequest,
    FileDisputeResponse,
    GetArbitrationVotesResponse,
    GetDisputeResponse,
    GetEvidenceResponse,
    SubmitArbitrationVoteRequest,
    SubmitArbitrationVoteResponse,
    SubmitEvidenceRequest,
    SubmitEvidenceResponse,
    VerifyEvidenceRequest,
    VerifyEvidenceResponse,
)
from ..auth import security

_logger = get_logger(__name__)

router = APIRouter(prefix="/disputes", tags=["disputes"])

# Optional imports - will be None if module not available
file_dispute = None
submit_evidence = None
verify_evidence = None
submit_arbitration_vote = None
authorize_arbitrator = None
get_active_disputes = None
get_authorized_arbitrators = None
get_arbitrator_disputes = None
get_user_disputes = None
get_dispute = None
get_dispute_evidence = None
get_arbitration_votes = None

try:
    from ..disputes import (
        authorize_arbitrator,
        file_dispute,
        get_active_disputes,
        get_arbitration_votes,
        get_arbitrator_disputes,
        get_authorized_arbitrators,
        get_dispute,
        get_dispute_evidence,
        get_user_disputes,
        submit_arbitration_vote,
        submit_evidence,
        verify_evidence,
    )
except ImportError as e:
    _logger.error("Disputes module not available: %s — affected endpoints will return 503", e)


@router.post("/file", summary="File a new dispute")
async def file_dispute_route(
    request: FileDisputeRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> FileDisputeResponse:
    """File a new dispute for a marketplace transaction"""
    if file_dispute is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await file_dispute(request, http_request, credentials)


@router.post("/evidence", summary="Submit evidence for a dispute")
async def submit_evidence_route(
    request: SubmitEvidenceRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> SubmitEvidenceResponse:
    """Submit evidence for a dispute"""
    if submit_evidence is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await submit_evidence(request, http_request, credentials)


@router.post("/verify-evidence", summary="Verify evidence (arbitrator only)")
async def verify_evidence_route(
    request: VerifyEvidenceRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> VerifyEvidenceResponse:
    """Verify evidence submitted in a dispute"""
    if verify_evidence is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await verify_evidence(request, http_request, credentials)


@router.post("/vote", summary="Submit arbitration vote (arbitrator only)")
async def submit_arbitration_vote_route(
    request: SubmitArbitrationVoteRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> SubmitArbitrationVoteResponse:
    """Submit an arbitration vote for a dispute"""
    if submit_arbitration_vote is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await submit_arbitration_vote(request, http_request, credentials)


@router.post("/arbitrators/authorize", summary="Authorize an arbitrator (admin only)")
async def authorize_arbitrator_route(
    request: AuthorizeArbitratorRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> AuthorizeArbitratorResponse:
    """Authorize a new arbitrator"""
    if authorize_arbitrator is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await authorize_arbitrator(request, http_request, credentials)


@router.get("/active", summary="Get all active disputes")
async def get_active_disputes_route() -> dict[str, Any]:
    """Get all active disputes"""
    if get_active_disputes is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await get_active_disputes()


@router.get("/arbitrators", summary="Get all authorized arbitrators")
async def get_authorized_arbitrators_route() -> dict[str, Any]:
    """Get all authorized arbitrators"""
    if get_authorized_arbitrators is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await get_authorized_arbitrators()


@router.get("/arbitrators/{arbitrator_address}", summary="Get disputes for an arbitrator")
async def get_arbitrator_disputes_route(arbitrator_address: str) -> dict[str, Any]:
    """Get all disputes assigned to an arbitrator"""
    if get_arbitrator_disputes is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await get_arbitrator_disputes(arbitrator_address)


@router.get("/user/{user_address}", summary="Get disputes for a user")
async def get_user_disputes_route(user_address: str) -> dict[str, Any]:
    """Get all disputes for a specific user"""
    if get_user_disputes is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await get_user_disputes(user_address)


@router.get("/{dispute_id}", summary="Get dispute details")
async def get_dispute_route(dispute_id: int) -> GetDisputeResponse:
    """Get details of a specific dispute"""
    if get_dispute is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await get_dispute(dispute_id)


@router.get("/{dispute_id}/evidence", summary="Get evidence for a dispute")
async def get_dispute_evidence_route(dispute_id: int) -> list[GetEvidenceResponse]:
    """Get all evidence submitted for a dispute"""
    if get_dispute_evidence is None:
        raise HTTPException(status_code=503, detail="Disputes module not available")
    return await get_dispute_evidence(dispute_id)


@router.get("/{dispute_id}/votes", summary="Get arbitration votes for a dispute")
async def get_arbitration_votes_route(dispute_id: int) -> list[GetArbitrationVotesResponse]:
    """Get all arbitration votes for a dispute"""
    return await get_arbitration_votes(dispute_id)
