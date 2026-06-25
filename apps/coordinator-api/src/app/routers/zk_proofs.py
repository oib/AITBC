"""
ZK Proofs Router - Zero-knowledge proof generation and verification

Provides REST API endpoints for:
- ZK proof generation for AI job receipts
- ZK proof verification
- Circuit information
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from ..contexts.zk_applications.services.zk_proofs import zk_proof_service

router = APIRouter(prefix="/zk", tags=["zk-proofs"])


class GenerateProofRequest(BaseModel):
    """Request to generate a ZK proof"""

    job_id: str
    miner_id: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    result_value: int
    pricing_rate: int
    privacy_level: str = "basic"


class VerifyProofRequest(BaseModel):
    """Request to verify a ZK proof"""

    proof: dict[str, Any]


class ProofResponse(BaseModel):
    """Response containing proof data"""

    success: bool
    proof: dict[str, Any]
    commitment: str
    timestamp: str


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
            job_id=req.job_id,
            miner_id=req.miner_id,
            input_data=req.input_data,
            output_data=req.output_data,
            result_value=req.result_value,
            pricing_rate=req.pricing_rate,
            privacy_level=req.privacy_level,
        )

        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error", "Proof generation failed"))

        return ProofResponse(
            success=True, proof=result["proof"], commitment=result["commitment"], timestamp=result["timestamp"]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Proof generation error: {str(e)}"
        ) from e


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

        result = await zk_service.verify_proof(req.proof)

        return VerificationResponse(
            verified=result["verified"],
            computation_correct=result["computation_correct"],
            privacy_preserved=result["privacy_preserved"],
            reason=result.get("reason", result.get("error", "Unknown")),
            commitment=result.get("commitment", "unknown"),
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Verification error: {str(e)}") from e


@router.get("/info", summary="Get circuit information")
@rate_limit(rate=100, per=60)
async def get_circuit_info(request: Request) -> dict[str, Any]:
    """Get information about the ZK circuit and setup parameters"""
    try:
        zk_service = zk_proof_service
        return zk_service.get_circuit_info()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get circuit info: {str(e)}"
        ) from e


@router.get("/health", summary="ZK service health check")
async def health_check(request: Request) -> dict[str, Any]:
    """Check if ZK proof service is operational"""
    try:
        zk_service = zk_proof_service
        info = zk_service.get_circuit_info()
        return {
            "status": "healthy",
            "circuit_type": info.get("circuit_type"),
            "verification_method": info.get("verification_method"),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
