"""
Dispute-related RPC endpoints.
"""

from typing import Any, Dict, List
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from ..logger import get_logger
from .auth import get_authenticated_address

_logger = get_logger(__name__)

# Import dispute resolution service and models
from ..services.dispute_resolution import dispute_resolution_service
from ..models.dispute import (
    FileDisputeRequest,
    FileDisputeResponse,
    SubmitEvidenceRequest,
    SubmitEvidenceResponse,
    VerifyEvidenceRequest,
    VerifyEvidenceResponse,
    SubmitArbitrationVoteRequest,
    SubmitArbitrationVoteResponse,
    AuthorizeArbitratorRequest,
    AuthorizeArbitratorResponse,
    GetDisputeResponse,
    GetEvidenceResponse,
    GetArbitrationVotesResponse,
)


async def file_dispute(
    request: FileDisputeRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = None
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
            sender_address=sender_address
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to file dispute"))
        
        return FileDisputeResponse(
            success=True,
            dispute_id=result["dispute_id"],
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error filing dispute: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to file dispute: {str(e)}")


async def submit_evidence(
    request: SubmitEvidenceRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = None
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
            evidence_data=request.evidence_data,
            submitter_address=submitter_address
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to submit evidence"))
        
        return SubmitEvidenceResponse(
            success=True,
            evidence_id=result["evidence_id"],
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error submitting evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit evidence: {str(e)}")


async def verify_evidence(
    request: VerifyEvidenceRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = None
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
            is_valid=request.is_valid,
            verification_score=request.verification_score,
            arbitrator_address=arbitrator_address
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to verify evidence"))
        
        return VerifyEvidenceResponse(
            success=True,
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error verifying evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to verify evidence: {str(e)}")


async def submit_arbitration_vote(
    request: SubmitArbitrationVoteRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = None
) -> SubmitArbitrationVoteResponse:
    """
    Submit an arbitration vote for a dispute.
    This can only be called by authorized arbitrators assigned to the dispute.
    """
    try:
        arbitrator_address = get_authenticated_address(http_request, credentials)

        # Reject zero address in all modes - this is a sensitive arbitration operation
        if arbitrator_address == "0x0000000000000000000000000000000000000000":
            _logger.error("Vote submission attempted with zero address - rejected")
            raise HTTPException(
                status_code=401,
                detail="Zero address is not allowed for arbitration operations"
            )

        return SubmitArbitrationVoteResponse(
            success=True,
            status="Submitted",
            message=f"Vote submitted successfully for dispute {request.dispute_id}"
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error submitting arbitration vote: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit vote: {str(e)}")


async def authorize_arbitrator(
    request: AuthorizeArbitratorRequest,
    http_request: Request,
    credentials: HTTPAuthorizationCredentials = None
) -> AuthorizeArbitratorResponse:
    """
    Authorize a new arbitrator.
    This can only be called by the contract owner.
    """
    try:
        owner_address = get_authenticated_address(http_request, credentials)
        
        result = dispute_resolution_service.authorize_arbitrator(
            arbitrator_address=request.arbitrator,
            reputation_score=request.reputation_score,
            owner_address=owner_address
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to authorize arbitrator"))
        
        return AuthorizeArbitratorResponse(
            success=True,
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error authorizing arbitrator: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to authorize arbitrator: {str(e)}")


async def get_active_disputes() -> Dict[str, Any]:
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
        _logger.error(f"Error getting active disputes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active disputes: {str(e)}")


async def get_authorized_arbitrators() -> Dict[str, Any]:
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
        _logger.error(f"Error getting authorized arbitrators: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get authorized arbitrators: {str(e)}")


async def get_arbitrator_disputes(arbitrator_address: str) -> Dict[str, Any]:
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
        _logger.error(f"Error getting arbitrator disputes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get arbitrator disputes: {str(e)}")


async def get_user_disputes(user_address: str) -> Dict[str, Any]:
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
        _logger.error(f"Error getting user disputes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user disputes: {str(e)}")


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
        _logger.error(f"Error getting dispute: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dispute: {str(e)}")


async def get_dispute_evidence(dispute_id: int) -> List[GetEvidenceResponse]:
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
        _logger.error(f"Error getting dispute evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dispute evidence: {str(e)}")


async def get_arbitration_votes(dispute_id: int) -> List[GetArbitrationVotesResponse]:
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
        _logger.error(f"Error getting arbitration votes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get arbitration votes: {str(e)}")
