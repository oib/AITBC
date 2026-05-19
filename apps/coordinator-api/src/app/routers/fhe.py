"""
FHE Router - Fully Homomorphic Encryption API endpoints

Provides REST API for:
- FHE context generation
- Data encryption/decryption
- Homomorphic operations
- Encrypted inference
"""

from __future__ import annotations

from typing import Any, Dict, List
import numpy as np

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..services.fhe_enhanced import get_fhe_provider


router = APIRouter(prefix="/fhe", tags=["fhe"])


class GenerateContextRequest(BaseModel):
    """Request to generate FHE context"""
    scheme: str = "bfv"
    poly_modulus_degree: int = 4096
    plain_modulus: int = 1032193


class EncryptRequest(BaseModel):
    """Request to encrypt data"""
    context_id: str
    data: List[float]


class DecryptRequest(BaseModel):
    """Request to decrypt data"""
    encrypted_data: Dict[str, Any]


class HomomorphicOpRequest(BaseModel):
    """Request for homomorphic operation"""
    context_id: str
    encrypted_a: Dict[str, Any]
    encrypted_b: Optional[Dict[str, Any]] = None
    scalar: Optional[float] = None
    plain_data: Optional[List[float]] = None


class InferenceRequest(BaseModel):
    """Request for encrypted inference"""
    context_id: str
    encrypted_input: Dict[str, Any]
    model: Dict[str, Any]


@router.post("/context/generate", summary="Generate FHE context")
async def generate_context(
    request: Request,
    req: GenerateContextRequest
) -> Dict[str, Any]:
    """Generate a new FHE encryption context with keys"""
    try:
        provider = get_fhe_provider()
        result = provider.generate_context(
            scheme=req.scheme,
            poly_modulus_degree=req.poly_modulus_degree,
            plain_modulus=req.plain_modulus
        )
        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate context: {str(e)}"
        )


@router.post("/encrypt", summary="Encrypt data")
async def encrypt_data(
    request: Request,
    req: EncryptRequest
) -> Dict[str, Any]:
    """Encrypt plaintext data using FHE"""
    try:
        provider = get_fhe_provider()
        encrypted = provider.encrypt(
            data=np.array(req.data),
            context_id=req.context_id
        )
        return {
            "success": True,
            "encrypted_data": encrypted.serialize(),
            "shape": encrypted.shape,
            "context_id": encrypted.context_id
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Encryption failed: {str(e)}"
        )


@router.post("/decrypt", summary="Decrypt data")
async def decrypt_data(
    request: Request,
    req: DecryptRequest
) -> Dict[str, Any]:
    """Decrypt FHE-encrypted data"""
    try:
        from ..services.fhe_enhanced import EncryptedVector
        
        provider = get_fhe_provider()
        encrypted = EncryptedVector.deserialize(req.encrypted_data)
        decrypted = provider.decrypt(encrypted)
        
        return {
            "success": True,
            "data": decrypted.tolist(),
            "shape": list(decrypted.shape),
            "dtype": str(decrypted.dtype)
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Decryption failed: {str(e)}"
        )


@router.post("/add", summary="Homomorphic addition")
async def homomorphic_add(
    request: Request,
    req: HomomorphicOpRequest
) -> Dict[str, Any]:
    """
    Perform homomorphic addition.
    
    Either E(a) + E(b) or E(a) + plaintext
    """
    try:
        from ..services.fhe_enhanced import EncryptedVector
        
        provider = get_fhe_provider()
        encrypted_a = EncryptedVector.deserialize(req.encrypted_a)
        
        if req.encrypted_b:
            # Ciphertext + Ciphertext
            encrypted_b = EncryptedVector.deserialize(req.encrypted_b)
            result = provider.add_cipher_cipher(encrypted_a, encrypted_b)
        elif req.plain_data:
            # Ciphertext + Plaintext
            result = provider.add_cipher_plain(
                encrypted_a,
                np.array(req.plain_data)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either encrypted_b or plain_data required"
            )
        
        return {
            "success": True,
            "result": result.serialize(),
            "operation": "add"
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Operation failed: {str(e)}"
        )


@router.post("/multiply-scalar", summary="Homomorphic scalar multiplication")
async def homomorphic_multiply(
    request: Request,
    req: HomomorphicOpRequest
) -> Dict[str, Any]:
    """Perform homomorphic multiplication by scalar: E(a) * s = E(a*s)"""
    try:
        from ..services.fhe_enhanced import EncryptedVector
        
        if req.scalar is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scalar required"
            )
        
        provider = get_fhe_provider()
        encrypted = EncryptedVector.deserialize(req.encrypted_a)
        result = provider.multiply_cipher_scalar(encrypted, req.scalar)
        
        return {
            "success": True,
            "result": result.serialize(),
            "operation": "multiply_scalar",
            "scalar": req.scalar
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Operation failed: {str(e)}"
        )


@router.post("/inference", summary="Encrypted inference")
async def encrypted_inference(
    request: Request,
    req: InferenceRequest
) -> Dict[str, Any]:
    """Perform ML inference on encrypted data"""
    try:
        from ..services.fhe_enhanced import EncryptedVector
        
        provider = get_fhe_provider()
        encrypted_input = EncryptedVector.deserialize(req.encrypted_input)
        
        result = provider.encrypted_inference(req.model, encrypted_input)
        
        return {
            "success": True,
            "encrypted_output": result.serialize(),
            "model_type": req.model.get("type", "unknown")
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {str(e)}"
        )


@router.get("/context/{context_id}", summary="Get context info")
async def get_context_info(
    request: Request,
    context_id: str
) -> Dict[str, Any]:
    """Get information about an FHE context"""
    try:
        provider = get_fhe_provider()
        return provider.get_context_info(context_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get context info: {str(e)}"
        )


@router.get("/health", summary="Health check")
async def fhe_health(request: Request) -> Dict[str, Any]:
    """Check FHE service health"""
    return {
        "status": "healthy",
        "fhe_available": True,
        "service": "fhe"
    }
