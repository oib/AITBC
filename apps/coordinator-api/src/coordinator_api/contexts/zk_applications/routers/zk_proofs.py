"""
ZK Proofs Router - Zero-knowledge proof generation and verification

Provides REST API endpoints for:
- ZK proof generation for AI job receipts
- ZK proof verification
- Circuit information
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from aitbc.rate_limiting import rate_limit

from ..services.zk_proofs import zk_proof_service
from coordinator_api.contexts.infrastructure.domain import Job
from coordinator_api.storage import get_session

router = APIRouter(prefix="/zk", tags=["zk-proofs"])


class GenerateProofRequest(BaseModel):
    """Request to generate a ZK proof"""

    circuit_name: str = "receipt_simple"
    inputs: dict[str, Any]
    private_inputs: dict[str, Any] | None = None


class VerifyProofRequest(BaseModel):
    """Request to verify a ZK proof.

    ``verification_key`` used to be a field here, passed straight to the verifier. A caller
    could generate their own Groth16 keypair, prove any statement, and submit proof and key
    together to be told ``verified: true``. The key is now chosen server-side from
    ``circuit_name``; a caller may say *which* circuit to check against, never *what to
    check with*.
    """

    proof: dict[str, Any]
    public_signals: list[str]
    circuit_name: str | None = None


class ProofResponse(BaseModel):
    """Response containing proof data"""

    success: bool
    proof: dict[str, Any]
    proof_id: str
    circuit_type: str
    public_signals: list[Any]


class VerificationResponse(BaseModel):
    """Response containing verification result"""

    verified: bool
    computation_correct: bool
    privacy_preserved: bool
    reason: str
    commitment: str


@router.post("/generate", response_model=ProofResponse, summary="Generate ZK proof")
@rate_limit(rate=20, per=60)
async def generate_proof(request: Request, req: GenerateProofRequest) -> ProofResponse:
    """
    Generate a zero-knowledge proof for AI computation.

    This creates a privacy-preserving proof that:
    - Computation was performed correctly
    - Results match claimed output
    - Without revealing computation details
    """
    try:
        zk_service = zk_proof_service

        result = await zk_service.generate_proof(
            circuit_name=req.circuit_name,
            inputs=req.inputs,
            private_inputs=req.private_inputs,
        )

        if result is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proof generation failed")

        return ProofResponse(
            success=True,
            proof=result["proof"],
            proof_id=result["proof_id"],
            circuit_type=result["circuit_type"],
            public_signals=result["public_signals"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.post("/verify", response_model=VerificationResponse, summary="Verify ZK proof")
@rate_limit(rate=50, per=60)
async def verify_proof(request: Request, req: VerifyProofRequest) -> VerificationResponse:
    """
    Verify a zero-knowledge proof.

    Checks:
    - Proof structure validity
    - Commitment correctness
    - Pairing equation satisfaction
    - Timestamp freshness
    """
    try:
        zk_service = zk_proof_service

        result = await zk_service.verify_proof(
            proof=req.proof,
            public_signals=req.public_signals,
            circuit_name=req.circuit_name,
        )

        return VerificationResponse(
            verified=result["verified"],
            computation_correct=result.get("computation_correct", False),
            privacy_preserved=result.get("privacy_preserved", False),
            reason=result.get("reason", result.get("error", "Unknown")),
            commitment=result.get("commitment", "unknown"),
        )

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.get("/info", summary="Get circuit information")
@rate_limit(rate=100, per=60)
async def get_circuit_info(request: Request) -> dict[str, Any]:
    """Get information about available ZK circuits and setup parameters"""
    try:
        zk_service = zk_proof_service
        return {
            "enabled": zk_service.is_enabled(),
            "available_circuits": list(zk_service.available_circuits.keys()),
        }
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


class VerifyJobReceiptRequest(BaseModel):
    """Request to verify the stored ZK receipt proof for a completed job."""

    job_id: str


@router.post("/receipt/verify", response_model=VerificationResponse, summary="Verify a job receipt's stored ZK proof")
@rate_limit(rate=50, per=60)
async def verify_job_receipt(
    request: Request,
    req: VerifyJobReceiptRequest,
    session: Session = Depends(get_session),
) -> VerificationResponse:
    """Verify the ZK receipt proof that was attached to a completed job."""
    try:
        job = session.get(Job, req.job_id)
        if not job or not job.receipt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job or receipt not found",
            )

        receipt = job.receipt if isinstance(job.receipt, dict) else {}
        zk_proof = receipt.get("zk_proof")
        if not zk_proof:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No ZK proof stored for this job",
            )

        zk_service = zk_proof_service
        result = await zk_service.verify_proof(
            proof=zk_proof["proof"],
            public_signals=zk_proof["public_signals"],
            circuit_name=zk_proof.get("circuit") or zk_proof.get("circuit_name"),
        )

        return VerificationResponse(
            verified=result["verified"],
            computation_correct=result.get("computation_correct", False),
            privacy_preserved=result.get("privacy_preserved", False),
            reason=result.get("reason", result.get("error", "Unknown")),
            commitment=result.get("commitment", "unknown"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.get("/health", summary="ZK service health check")
async def health_check(request: Request) -> dict[str, Any]:
    """Check if ZK proof service is operational"""
    try:
        zk_service = zk_proof_service
        return {
            "status": "healthy" if zk_service.is_enabled() else "disabled",
            "available_circuits": list(zk_service.available_circuits.keys()),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
