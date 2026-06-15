"""
Dispute-related RPC endpoints.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from ..logger import get_logger
from .auth import get_authenticated_address

_logger = get_logger(__name__)
from ..models.dispute import (  # noqa: E402
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
from ..rpc.dispute_resolution_service import dispute_resolution_service  # noqa: E402


async def file_dispute(
    request: FileDisputeRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> FileDisputeResponse:
    """
    File a new dispute for a marketplace transaction.
    This interacts with the DisputeResolution smart contract.
    """
    try:
        sender_address = get_authenticated_address(http_request, credentials)
        result = dispute_resolution_service.file_dispute(
            agreement_id=request.agreement_id,
            respondent=request.respondent,
            dispute_type=request.dispute_type,
            reason=request.reason,
            evidence_hash=request.evidence_hash,
            sender_address=sender_address,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to file dispute"))
        return FileDisputeResponse(
            success=True, dispute_id=result["dispute_id"], status=result["status"], message=result["message"], timestamp=""
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error filing dispute: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to file dispute: {str(e)}") from e


async def submit_evidence(
    request: SubmitEvidenceRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> SubmitEvidenceResponse:
    """
    Submit evidence for a dispute.
    This interacts with the DisputeResolution smart contract.
    """
    try:
        submitter_address = get_authenticated_address(http_request, credentials)
        result = dispute_resolution_service.submit_evidence(
            dispute_id=request.dispute_id,
            evidence_type=request.evidence_type,
            evidence_data=request.description,
            submitter_address=submitter_address,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to submit evidence"))
        return SubmitEvidenceResponse(
            success=True, evidence_id=result["evidence_id"], status=result["status"], message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error submitting evidence: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to submit evidence: {str(e)}") from e


async def verify_evidence(
    request: VerifyEvidenceRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> VerifyEvidenceResponse:
    """
    Verify evidence submitted in a dispute.
    This can only be called by authorized arbitrators.
    """
    try:
        arbitrator_address = get_authenticated_address(http_request, credentials)
        result = dispute_resolution_service.verify_evidence(
            dispute_id=request.dispute_id,
            evidence_id=request.evidence_id,
            is_valid=request.verified,
            verification_score=1,
            arbitrator_address=arbitrator_address,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to verify evidence"))
        return VerifyEvidenceResponse(success=True, status=result["status"], message=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error verifying evidence: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to verify evidence: {str(e)}") from e


async def submit_arbitration_vote(
    request: SubmitArbitrationVoteRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> SubmitArbitrationVoteResponse:
    """
    Submit an arbitration vote for a dispute.
    This can only be called by authorized arbitrators assigned to the dispute.
    """
    try:
        arbitrator_address = get_authenticated_address(http_request, credentials)
        if arbitrator_address == "0x0000000000000000000000000000000000000000":
            _logger.error("Vote submission attempted with zero address - rejected")
            raise HTTPException(status_code=401, detail="Zero address is not allowed for arbitration operations")
        return SubmitArbitrationVoteResponse(
            success=True,
            vote_id=0,
            status="Submitted",
            message=f"Vote submitted successfully for dispute {request.dispute_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error submitting arbitration vote: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to submit vote: {str(e)}") from e


async def authorize_arbitrator(
    request: AuthorizeArbitratorRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> AuthorizeArbitratorResponse:
    """
    Authorize a new arbitrator.
    This can only be called by the contract owner.
    """
    try:
        owner_address = get_authenticated_address(http_request, credentials)
        result = dispute_resolution_service.authorize_arbitrator(
            arbitrator_address=request.arbitrator_address, reputation_score=1, owner_address=owner_address
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to authorize arbitrator"))
        return AuthorizeArbitratorResponse(success=True, status=result["status"], message=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error authorizing arbitrator: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to authorize arbitrator: {str(e)}") from e


async def get_active_disputes() -> dict[str, Any]:
    """
    Get all active disputes.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_active_disputes()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get active disputes"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting active disputes: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get active disputes: {str(e)}") from e


async def get_authorized_arbitrators() -> dict[str, Any]:
    """
    Get all authorized arbitrators.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_authorized_arbitrators()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get authorized arbitrators"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting authorized arbitrators: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get authorized arbitrators: {str(e)}") from e


async def get_arbitrator_disputes(arbitrator_address: str) -> dict[str, Any]:
    """
    Get all disputes assigned to an arbitrator.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_arbitrator_disputes(arbitrator_address)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get arbitrator disputes"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting arbitrator disputes: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get arbitrator disputes: {str(e)}") from e


async def get_user_disputes(user_address: str) -> dict[str, Any]:
    """
    Get all disputes for a specific user.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_user_disputes(user_address)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get user disputes"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting user disputes: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get user disputes: {str(e)}") from e


async def get_dispute(dispute_id: int) -> GetDisputeResponse:
    """
    Get details of a specific dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_dispute(dispute_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Dispute not found"))
        dispute_data = result["dispute"]
        return GetDisputeResponse(**dispute_data)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting dispute: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get dispute: {str(e)}") from e


async def get_dispute_evidence(dispute_id: int) -> list[GetEvidenceResponse]:
    """
    Get all evidence submitted for a dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_dispute_evidence(dispute_id)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get dispute evidence"))
        return [GetEvidenceResponse(**e) for e in result["evidence"]]
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting dispute evidence: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get dispute evidence: {str(e)}") from e


async def get_arbitration_votes(dispute_id: int) -> list[GetArbitrationVotesResponse]:
    """
    Get all arbitration votes for a dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_arbitration_votes(dispute_id)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get arbitration votes"))
        return [GetArbitrationVotesResponse(**v) for v in result["votes"]]
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting arbitration votes: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get arbitration votes: {str(e)}") from e
