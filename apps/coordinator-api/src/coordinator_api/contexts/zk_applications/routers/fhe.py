"""FHE Router - Fully Homomorphic Encryption API endpoints.

Endpoints use the TenSEAL-backed FHE service when ``tenseal`` is installed,
otherwise return 503. Install the optional ``[fhe]`` dependency group or
``pip install tenseal`` to enable them.
"""

from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ....auth import AuthDep
from ..services.fhe_service import EncryptedData, FHEService, FHEContext

router = APIRouter(prefix="/fhe", tags=["fhe"])

_service = FHEService()

# In-memory registries keyed by UUID. Encrypted payloads are returned as
# base64 so clients can store or pass them without binary transport issues.
_contexts: dict[str, FHEContext] = {}
_encrypted: dict[str, EncryptedData] = {}


class GenerateContextRequest(BaseModel):
    """Request to generate FHE context"""

    scheme: str = "ckks"
    poly_modulus_degree: int = 8192
    plain_modulus: int = 1032193


class EncryptRequest(BaseModel):
    """Request to encrypt data"""

    context_id: str
    data: list[float]


class EncryptedRef(BaseModel):
    """Reference to an encrypted payload stored by the server."""

    encrypted_id: str = Field(..., description="Server-side encrypted payload ID")


class DecryptRequest(BaseModel):
    """Request to decrypt data"""

    encrypted_id: str


class HomomorphicOpRequest(BaseModel):
    """Request for homomorphic operation"""

    context_id: str
    encrypted_a_id: str
    encrypted_b_id: str | None = None
    scalar: float | None = None


class InferenceRequest(BaseModel):
    """Request for encrypted inference"""

    context_id: str
    encrypted_input_id: str
    model: dict[str, Any]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _from_b64(text: str) -> bytes:
    return base64.b64decode(text)


def _ensure_available() -> None:
    if not _service.get_provider().available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FHE service is unavailable; install 'tenseal' to enable FHE operations",
        )


def _encrypted_response(encrypted: EncryptedData) -> dict[str, Any]:
    encrypted_id = uuid4().hex
    _encrypted[encrypted_id] = encrypted
    return {
        "encrypted_id": encrypted_id,
        "context_id": None,  # caller already knows the context
        "ciphertext_b64": _b64(encrypted.ciphertext),
        "shape": list(encrypted.shape),
        "dtype": encrypted.dtype,
    }


def _context_response(context_id: str, context: FHEContext) -> dict[str, Any]:
    return {
        "context_id": context_id,
        "scheme": context.scheme,
        "poly_modulus_degree": context.poly_modulus_degree,
        "scale": context.scale,
    }


@router.post("/context/generate", summary="Generate FHE context")
async def generate_context(req: GenerateContextRequest, current_user: AuthDep) -> dict[str, Any]:
    """Generate a new FHE encryption context with keys."""
    _ensure_available()
    try:
        context = _service.generate_fhe_context(
            scheme=req.scheme,
            poly_modulus_degree=req.poly_modulus_degree,
            plain_modulus=req.plain_modulus,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    context_id = uuid4().hex
    _contexts[context_id] = context
    return _context_response(context_id, context)


@router.post("/encrypt", summary="Encrypt data")
async def encrypt_data(req: EncryptRequest, current_user: AuthDep) -> dict[str, Any]:
    """Encrypt plaintext data using FHE."""
    _ensure_available()
    if req.context_id not in _contexts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    context = _contexts[req.context_id]
    data = np.array(req.data, dtype=np.float64)
    try:
        encrypted = _service.encrypt_ml_data(data, context)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(encrypted)


@router.post("/decrypt", summary="Decrypt data")
async def decrypt_data(req: DecryptRequest, current_user: AuthDep) -> dict[str, Any]:
    """Decrypt FHE-encrypted data."""
    _ensure_available()
    if req.encrypted_id not in _encrypted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    encrypted = _encrypted[req.encrypted_id]
    try:
        plaintext = _service.decrypt_ml_data(encrypted)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"plaintext": plaintext.tolist()}


@router.post("/add", summary="Homomorphic addition")
async def homomorphic_add(req: HomomorphicOpRequest, current_user: AuthDep) -> dict[str, Any]:
    """Perform homomorphic addition: E(a) + E(b) = E(a + b)."""
    _ensure_available()
    if req.context_id not in _contexts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    if not req.encrypted_b_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="encrypted_b_id is required")
    if req.encrypted_a_id not in _encrypted or req.encrypted_b_id not in _encrypted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        result = _service.add(_encrypted[req.encrypted_a_id], _encrypted[req.encrypted_b_id])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(result)


@router.post("/multiply-scalar", summary="Homomorphic scalar multiplication")
async def homomorphic_multiply(req: HomomorphicOpRequest, current_user: AuthDep) -> dict[str, Any]:
    """Perform homomorphic multiplication by scalar: E(a) * s = E(a*s)."""
    _ensure_available()
    if req.context_id not in _contexts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    if req.scalar is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scalar is required")
    if req.encrypted_a_id not in _encrypted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        result = _service.multiply_scalar(_encrypted[req.encrypted_a_id], float(req.scalar))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(result)


@router.post("/inference", summary="Encrypted inference")
async def encrypted_inference(req: InferenceRequest, current_user: AuthDep) -> dict[str, Any]:
    """Perform ML inference on encrypted data."""
    _ensure_available()
    if req.context_id not in _contexts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    if req.encrypted_input_id not in _encrypted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        result = _service.encrypted_inference(req.model, _encrypted[req.encrypted_input_id])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(result)


@router.get("/context/{context_id}", summary="Get context info")
async def get_context_info(context_id: str, current_user: AuthDep) -> dict[str, Any]:
    """Get information about an FHE context."""
    _ensure_available()
    if context_id not in _contexts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    return _context_response(context_id, _contexts[context_id])


@router.get("/health", summary="Health check")
async def fhe_health(current_user: AuthDep) -> dict[str, Any]:
    """Check FHE service health."""
    providers = _service.list_providers()
    return {
        "status": "available" if _service.get_provider().available else "unavailable",
        "fhe_available": _service.get_provider().available,
        "service": "fhe",
        "providers": providers,
    }
