"""FHE Router - Fully Homomorphic Encryption API endpoints.

Endpoints use the TenSEAL-backed FHE service when ``tenseal`` is installed,
otherwise return 503. Install the optional ``[fhe]`` dependency group or
``pip install tenseal`` to enable them.
"""

from __future__ import annotations

import base64
import threading
import time
from collections import OrderedDict
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator

from ....auth import AuthDep
from ..services.fhe_service import EncryptedData, FHEService, FHEContext
from aitbc.rate_limiting import rate_limit

router = APIRouter(prefix="/fhe", tags=["fhe"])

_service: FHEService | None = None


def _get_service() -> FHEService:
    """Construct the FHE service on first endpoint use, not at import.

    ``FHEService()`` probes every provider backend (tenseal, openfhe, ...)
    in ``__init__``; tenseal pulls in numpy, so constructing it here kept
    ~9.4s of numpy import plus RSS on every coordinator-api start even
    though the FHE endpoints are rarely hit.
    """
    global _service
    if _service is None:
        _service = FHEService()
    return _service


# In-memory registries keyed by UUID. Encrypted payloads are returned as
# base64 so clients can store or pass them without binary transport issues.
#
# Both registries are bounded (issue #3037): every stored FHEContext or
# EncryptedData can hold hundreds of MB of serialized keys/ciphertext at
# large ring dimensions, and the endpoints admit any authenticated client,
# so unbounded growth would let a caller exhaust coordinator-api memory.
# Entries expire after a TTL and the stores evict oldest-first past a cap.
# 50 contexts / 500 ciphertexts / 1h TTL is generous for interactive use —
# a legitimate job needs only a handful of each — while bounding worst-case
# retention. Contexts and ciphertexts are ephemeral compute artifacts;
# clients that need durability should keep the base64 payloads they were
# already given.
_CONTEXT_TTL_SECONDS = 3600.0
_ENCRYPTED_TTL_SECONDS = 3600.0
_MAX_CONTEXTS = 50
_MAX_ENCRYPTED = 500

_registry_lock = threading.Lock()
# id -> (value, monotonic expiry); OrderedDict keeps oldest-first eviction.
_contexts: OrderedDict[str, tuple[FHEContext, float]] = OrderedDict()
_encrypted: OrderedDict[str, tuple[EncryptedData, float]] = OrderedDict()


def _sweep(store: OrderedDict[str, tuple[Any, float]], now: float) -> None:
    """Drop expired entries."""
    expired = [key for key, (_, expires_at) in store.items() if expires_at <= now]
    for key in expired:
        store.pop(key, None)


def _store_put(
    store: OrderedDict[str, tuple[Any, float]],
    key: str,
    value: Any,
    cap: int,
    ttl_seconds: float,
) -> None:
    now = time.monotonic()
    _sweep(store, now)
    store[key] = (value, now + ttl_seconds)
    store.move_to_end(key)
    while len(store) > cap:
        store.popitem(last=False)


def _store_get(store: OrderedDict[str, tuple[Any, float]], key: str) -> Any | None:
    """Return a live entry; None if absent or expired.

    Reads refresh recency (LRU order) but not the expiry timestamp — the
    TTL runs from creation so a forgotten entry cannot be kept alive
    forever by polling.
    """
    entry = store.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at <= time.monotonic():
        store.pop(key, None)
        return None
    store.move_to_end(key)
    return value


def _put_context(context_id: str, context: FHEContext) -> None:
    with _registry_lock:
        _store_put(_contexts, context_id, context, _MAX_CONTEXTS, _CONTEXT_TTL_SECONDS)


def _get_context(context_id: str) -> FHEContext | None:
    with _registry_lock:
        return _store_get(_contexts, context_id)


def _put_encrypted(encrypted_id: str, encrypted: EncryptedData) -> None:
    with _registry_lock:
        _store_put(_encrypted, encrypted_id, encrypted, _MAX_ENCRYPTED, _ENCRYPTED_TTL_SECONDS)


def _get_encrypted(encrypted_id: str) -> EncryptedData | None:
    with _registry_lock:
        return _store_get(_encrypted, encrypted_id)


# Ring dimensions supported by both FHE backends: powers of two between
# 4096 and 32768 (TenSEAL's valid set in that range is exactly the powers
# of two; OpenFHE accepts any power of two >= 1024). Larger degrees grow
# context/key/ciphertext memory roughly linearly and are the main memory
# risk behind #3037, so the API rejects them outright.
_MIN_POLY_MODULUS_DEGREE = 4096
_MAX_POLY_MODULUS_DEGREE = 32768


class GenerateContextRequest(BaseModel):
    """Request to generate FHE context"""

    scheme: str = "ckks"
    poly_modulus_degree: int = Field(default=8192, ge=_MIN_POLY_MODULUS_DEGREE, le=_MAX_POLY_MODULUS_DEGREE)
    plain_modulus: int = 1032193

    @field_validator("poly_modulus_degree")
    @classmethod
    def _degree_must_be_power_of_two(cls, value: int) -> int:
        if value & (value - 1) != 0:
            raise ValueError("poly_modulus_degree must be a power of two")
        return value


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
    try:
        provider = _get_service().get_provider()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FHE provider is unavailable",
        ) from exc
    if not provider.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FHE provider is unavailable; install 'tenseal' to enable FHE operations",
        )


def _encrypted_response(encrypted: EncryptedData) -> dict[str, Any]:
    encrypted_id = uuid4().hex
    _put_encrypted(encrypted_id, encrypted)
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
@rate_limit(rate=30, per=60)
def generate_context(req: GenerateContextRequest, current_user: AuthDep, *, request: Request) -> dict[str, Any]:
    """Generate a new FHE encryption context with keys."""
    _ensure_available()
    try:
        context = _get_service().generate_fhe_context(
            scheme=req.scheme,
            poly_modulus_degree=req.poly_modulus_degree,
            plain_modulus=req.plain_modulus,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    context_id = uuid4().hex
    _put_context(context_id, context)
    return _context_response(context_id, context)


@router.post("/encrypt", summary="Encrypt data")
@rate_limit(rate=30, per=60)
def encrypt_data(req: EncryptRequest, current_user: AuthDep, *, request: Request) -> dict[str, Any]:
    """Encrypt plaintext data using FHE."""
    _ensure_available()
    context = _get_context(req.context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    import numpy as np

    data = np.array(req.data, dtype=np.float64)
    try:
        encrypted = _get_service().encrypt_ml_data(data, context)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(encrypted)


@router.post("/decrypt", summary="Decrypt data")
@rate_limit(rate=30, per=60)
def decrypt_data(req: DecryptRequest, current_user: AuthDep, *, request: Request) -> dict[str, Any]:
    """Decrypt FHE-encrypted data."""
    _ensure_available()
    encrypted = _get_encrypted(req.encrypted_id)
    if encrypted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        plaintext = _get_service().decrypt_ml_data(encrypted)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"plaintext": plaintext.tolist()}


@router.post("/add", summary="Homomorphic addition")
@rate_limit(rate=30, per=60)
def homomorphic_add(req: HomomorphicOpRequest, current_user: AuthDep, *, request: Request) -> dict[str, Any]:
    """Perform homomorphic addition: E(a) + E(b) = E(a + b)."""
    _ensure_available()
    if _get_context(req.context_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    if not req.encrypted_b_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="encrypted_b_id is required")
    encrypted_a = _get_encrypted(req.encrypted_a_id)
    encrypted_b = _get_encrypted(req.encrypted_b_id)
    if encrypted_a is None or encrypted_b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        result = _get_service().add(encrypted_a, encrypted_b)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(result)


@router.post("/multiply-scalar", summary="Homomorphic scalar multiplication")
@rate_limit(rate=30, per=60)
def homomorphic_multiply(req: HomomorphicOpRequest, current_user: AuthDep, *, request: Request) -> dict[str, Any]:
    """Perform homomorphic multiplication by scalar: E(a) * s = E(a*s)."""
    _ensure_available()
    if _get_context(req.context_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    if req.scalar is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scalar is required")
    encrypted_a = _get_encrypted(req.encrypted_a_id)
    if encrypted_a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        result = _get_service().multiply_scalar(encrypted_a, float(req.scalar))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(result)


@router.post("/inference", summary="Encrypted inference")
@rate_limit(rate=30, per=60)
def encrypted_inference(req: InferenceRequest, current_user: AuthDep, *, request: Request) -> dict[str, Any]:
    """Perform ML inference on encrypted data."""
    _ensure_available()
    if _get_context(req.context_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    encrypted_input = _get_encrypted(req.encrypted_input_id)
    if encrypted_input is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encrypted payload not found")
    try:
        result = _get_service().encrypted_inference(req.model, encrypted_input)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _encrypted_response(result)


@router.get("/context/{context_id}", summary="Get context info")
def get_context_info(context_id: str, current_user: AuthDep) -> dict[str, Any]:
    """Get information about an FHE context."""
    _ensure_available()
    context = _get_context(context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FHE context not found")
    return _context_response(context_id, context)


@router.get("/health", summary="Health check")
def fhe_health(current_user: AuthDep) -> dict[str, Any]:
    """Check FHE service health."""
    providers = _get_service().list_providers()
    try:
        provider = _get_service().get_provider()
        available = provider.available
    except RuntimeError:
        available = False
    return {
        "status": "available" if available else "unavailable",
        "fhe_available": available,
        "service": "fhe",
        "providers": providers,
    }
