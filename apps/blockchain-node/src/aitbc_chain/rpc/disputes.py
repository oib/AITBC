"""
Dispute-related RPC endpoints.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from aitbc.blockchain.dispute_auth import AUTH_FIELDS, dispute_sign_data
from aitbc.crypto.signature_recovery import canonical_address

from ..logger import get_logger
from ..models.dispute import (
    AuthorizeArbitratorRequest,
    AuthorizeArbitratorResponse,
    FileDisputeRequest,
    FileDisputeResponse,
    GetArbitrationVotesResponse,
    GetDisputeResponse,
    GetEvidenceResponse,
    RevokeArbitratorRequest,
    RevokeArbitratorResponse,
    SubmitArbitrationVoteRequest,
    SubmitArbitrationVoteResponse,
    SubmitEvidenceRequest,
    SubmitEvidenceResponse,
    VerifyEvidenceRequest,
    VerifyEvidenceResponse,
)
from ..rpc.dispute_resolution_service import dispute_resolution_service
from .auth import get_authenticated_address
from .utils import check_signed_request_freshness, verify_request_signature

_logger = get_logger(__name__)


def _claimed_wallet_address(http_request: Request | None) -> str:
    """Parse ``X-Wallet-Address`` as a *claimed* identity — no trust decision.

    #3052: on the dispute mutations the header only names the address the
    caller must prove key control of via ``signature``; it is never accepted
    on its own, so ``TRUST_X_WALLET_ADDRESS`` and the loopback check no
    longer gate these routes. Format validation matches
    ``get_authenticated_address`` so malformed claims still 401.
    """
    raw = http_request.headers.get("X-Wallet-Address") if http_request is not None else None
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide X-Wallet-Address and a wallet signature over the request.",
        )
    try:
        address = canonical_address(raw)
    except (ValueError, TypeError, AttributeError):
        _logger.warning("Invalid wallet address format in X-Wallet-Address header: %s", raw)
        raise HTTPException(status_code=401, detail="Invalid wallet address format") from None
    if not address.startswith("0x") or len(address) != 42:
        _logger.warning("Invalid wallet address format in X-Wallet-Address header: %s", raw)
        raise HTTPException(status_code=401, detail="Invalid wallet address format")
    return address


def _signed_payload(request: BaseModel) -> dict[str, Any]:
    """Business fields the client actually posted — the signed payload.

    Restricted to ``model_fields_set`` so pydantic defaults the client never
    sent (e.g. vote ``confidence``) are not folded into the signature; the
    CLI signs exactly the JSON it posts.
    """
    signed_fields = set(request.model_fields_set) - set(AUTH_FIELDS)
    return request.model_dump(include=signed_fields)


def get_signed_dispute_address(
    http_request: Request | None,
    *,
    action: str,
    signature: str | None,
    issued_at: int | None,
    nonce: str | None,
    payload: dict[str, Any],
) -> str:
    """Authenticate a dispute mutation by wallet signature (#3052).

    Returns the claimed address once the signature over
    ``dispute_sign_data(action, address, payload, issued_at, nonce)``
    recovers to it and the freshness/nonce replay guard passes. Missing
    credentials answer 401; a present-but-wrong, stale or replayed proof
    answers 403.
    """
    address = _claimed_wallet_address(http_request)
    if not signature or not isinstance(signature, str):
        raise HTTPException(
            status_code=401,
            detail="Wallet signature required. Sign the request per aitbc.blockchain.dispute_auth.",
        )
    sign_data = dispute_sign_data(
        action=action,
        address=address,
        payload=payload,
        issued_at=issued_at if isinstance(issued_at, int) and not isinstance(issued_at, bool) else 0,
        nonce=nonce if isinstance(nonce, str) else "",
    )
    if not verify_request_signature(address, signature, sign_data):
        _logger.warning("Rejected dispute mutation %s: invalid wallet signature for %s", action, address)
        raise HTTPException(status_code=403, detail="Invalid wallet signature")
    check_signed_request_freshness(sign_data, nonce_key=f"dispute:{action}:{address.lower()}:{nonce}")
    return address


def _raise_for_failed_dispute_call(result: dict[str, Any], fallback_detail: str) -> None:
    """Map a service-level ``{"success": False}`` result to an HTTPException.

    A "not found" error is a 404 (unknown dispute id); any other failure
    stays a 500. Keeps the evidence/votes reads consistent with
    ``get_dispute`` instead of leaking a 500 for a missing resource.
    """
    detail = result.get("error") or fallback_detail
    status_code = 404 if "not found" in str(detail).lower() else 500
    raise HTTPException(status_code=status_code, detail=detail)


def file_dispute(
    request: FileDisputeRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> FileDisputeResponse:
    """
    File a new dispute for a market transaction.
    This interacts with the DisputeResolution smart contract.
    """
    try:
        sender_address = get_signed_dispute_address(
            http_request,
            action="rpc/disputes/file",
            signature=request.signature,
            issued_at=request.issued_at,
            nonce=request.nonce,
            payload=_signed_payload(request),
        )
        result = dispute_resolution_service.file_dispute(
            agreement_id=request.agreement_id,
            respondent=request.respondent,
            dispute_type=request.dispute_type,
            reason=request.reason,
            evidence_hash=request.evidence_hash,
            sender_address=sender_address,
        )
        if not result.get("success"):
            detail = result.get("error", "Failed to file dispute")
            lowered = str(detail).lower()
            # A bad dispute_type surfaces from the contract as a ValueError
            # ("... is not a valid DisputeType") — a client error, not a 500
            # (#2288). The request model already rejects unknown types with
            # 422; this covers any path that reaches the service unvalidated.
            if "not a valid" in lowered or "invalid dispute" in lowered:
                raise HTTPException(status_code=400, detail=detail)
            if "not found" in lowered:
                raise HTTPException(status_code=404, detail=detail)
            raise HTTPException(status_code=500, detail=detail)
        return FileDisputeResponse(
            success=True, dispute_id=result["dispute_id"], status=result["status"], message=result["message"], timestamp=""
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error filing dispute: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def submit_evidence(
    request: SubmitEvidenceRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> SubmitEvidenceResponse:
    """
    Submit evidence for a dispute.
    This interacts with the DisputeResolution smart contract.
    """
    try:
        submitter_address = get_signed_dispute_address(
            http_request,
            action="rpc/disputes/evidence",
            signature=request.signature,
            issued_at=request.issued_at,
            nonce=request.nonce,
            payload=_signed_payload(request),
        )
        result = dispute_resolution_service.submit_evidence(
            dispute_id=request.dispute_id,
            evidence_type=request.evidence_type,
            evidence_data=request.description,
            submitter_address=submitter_address,
            evidence_hash=request.evidence_hash,
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
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def verify_evidence(
    request: VerifyEvidenceRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> VerifyEvidenceResponse:
    """
    Verify evidence submitted in a dispute.
    This can only be called by authorized arbitrators.
    """
    try:
        arbitrator_address = get_signed_dispute_address(
            http_request,
            action="rpc/disputes/verify-evidence",
            signature=request.signature,
            issued_at=request.issued_at,
            nonce=request.nonce,
            payload=_signed_payload(request),
        )
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
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def submit_arbitration_vote(
    request: SubmitArbitrationVoteRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> SubmitArbitrationVoteResponse:
    """
    Submit an arbitration vote for a dispute.
    This can only be called by authorized arbitrators assigned to the dispute.
    """
    try:
        arbitrator_address = get_signed_dispute_address(
            http_request,
            action="rpc/disputes/vote",
            signature=request.signature,
            issued_at=request.issued_at,
            nonce=request.nonce,
            payload=_signed_payload(request),
        )
        if arbitrator_address == "0x0000000000000000000000000000000000000000":
            _logger.error("Vote submission attempted with zero address - rejected")
            raise HTTPException(status_code=401, detail="Zero address is not allowed for arbitration operations")
        # "plaintiff" is the dispute initiator (the filer); "defendant" the respondent.
        vote_in_favor_of_initiator = request.vote == "plaintiff"
        result = dispute_resolution_service.submit_arbitration_vote(
            dispute_id=request.dispute_id,
            vote_in_favor_of_initiator=vote_in_favor_of_initiator,
            confidence=request.confidence,
            reasoning=request.reasoning,
            arbitrator_address=arbitrator_address,
        )
        if not result.get("success"):
            detail = result.get("error", "Failed to submit arbitration vote")
            lowered = str(detail).lower()
            if "not found" in lowered:
                raise HTTPException(status_code=404, detail=detail)
            if "arbitrator" in lowered:
                raise HTTPException(status_code=403, detail=detail)
            raise HTTPException(status_code=500, detail=detail)
        return SubmitArbitrationVoteResponse(status=result.get("status", "Submitted"), vote_id=result.get("vote_id", 0))
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error submitting arbitration vote: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def authorize_arbitrator(
    request: AuthorizeArbitratorRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> AuthorizeArbitratorResponse:
    """
    Authorize a new arbitrator.
    This can only be called by the contract owner.

    #2524: ``authorized=false`` is not a grant — it must not silently
    authorize anyway. Revocation lives at ``/arbitrators/revoke``.
    """
    try:
        owner_address = get_authenticated_address(http_request, credentials)
        if request.authorized is False:
            raise HTTPException(
                status_code=400,
                detail="authorized=false is not a grant; use POST /rpc/disputes/arbitrators/revoke",
            )
        result = dispute_resolution_service.authorize_arbitrator(
            arbitrator_address=request.arbitrator_address,
            reputation_score=1,
            owner_address=owner_address,
            owner_signature=request.owner_signature,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to authorize arbitrator"))
        return AuthorizeArbitratorResponse(success=True, status=result["status"], message=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error authorizing arbitrator: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def revoke_arbitrator(
    request: RevokeArbitratorRequest, http_request: Request, credentials: HTTPAuthorizationCredentials | None = None
) -> RevokeArbitratorResponse:
    """
    Revoke an owner-granted arbitrator.
    This can only be called by the contract owner.
    """
    try:
        owner_address = get_authenticated_address(http_request, credentials)
        result = dispute_resolution_service.revoke_arbitrator(
            arbitrator_address=request.arbitrator_address,
            owner_address=owner_address,
            owner_signature=request.owner_signature,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to revoke arbitrator"))
        return RevokeArbitratorResponse(success=True, status=result["status"], message=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error revoking arbitrator: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_active_disputes() -> dict[str, Any]:
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
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_authorized_arbitrators() -> dict[str, Any]:
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
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_arbitrator_disputes(arbitrator_address: str) -> dict[str, Any]:
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
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_user_disputes(user_address: str) -> dict[str, Any]:
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
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_dispute(dispute_id: int) -> GetDisputeResponse:
    """
    Get details of a specific dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_dispute(dispute_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Dispute not found"))
        d = result["dispute"]
        # Map contract dataclass fields to response model fields
        dispute_data = {
            "dispute_id": d["dispute_id"],
            "agreement_id": d["agreement_id"],
            "plaintiff": d.get("initiator", ""),
            "respondent": d.get("respondent", ""),
            "dispute_type": d.get("dispute_type", ""),
            "reason": d.get("reason", ""),
            "status": d.get("status", ""),
            "created_at": str(d.get("filing_time", "")),
            "winner": d.get("winner"),
            "resolution_reason": d.get("resolution_reason", ""),
            "is_escalated": bool(d.get("is_escalated", False)),
            "evidence": [],
            "votes": [],
        }
        return GetDisputeResponse(**dispute_data)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting dispute: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_dispute_evidence(dispute_id: int) -> list[GetEvidenceResponse]:
    """
    Get all evidence submitted for a dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_dispute_evidence(dispute_id)
        if not result.get("success"):
            _raise_for_failed_dispute_call(result, "Failed to get dispute evidence")
        evidence_list = []
        for e in result["evidence"]:
            evidence_list.append(
                GetEvidenceResponse(
                    evidence_id=e["evidence_id"],
                    dispute_id=e["dispute_id"],
                    evidence_hash=e.get("evidence_hash", ""),
                    evidence_type=e.get("evidence_type", ""),
                    description=e.get("evidence_data", ""),
                    submitted_by=e.get("submitter", ""),
                    verified=e.get("is_valid", False),
                    created_at=str(e.get("submission_time", "")),
                )
            )
        return evidence_list
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting dispute evidence: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def get_arbitration_votes(dispute_id: int) -> list[GetArbitrationVotesResponse]:
    """
    Get all arbitration votes for a dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_arbitration_votes(dispute_id)
        if not result.get("success"):
            _raise_for_failed_dispute_call(result, "Failed to get arbitration votes")
        return [GetArbitrationVotesResponse(dispute_id=dispute_id, votes=[vote]) for vote in result["votes"]]
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error getting arbitration votes: %s", e)
        _logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
