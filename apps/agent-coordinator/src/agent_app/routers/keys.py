"""Public key exchange endpoints for the Agent Coordinator."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..encryption import public_keys

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agent/keys", tags=["agent-keys"])


class RegisterKeyRequest(BaseModel):
    """Request to register a public key for an agent."""

    agent_id: str = Field(..., description="Agent ID that owns the key")
    public_key: str = Field(..., description="PEM-encoded public key (base64)")
    key_id: str = Field(default="", description="Optional key identifier")


class KeyResponse(BaseModel):
    """Response containing a public key."""

    agent_id: str
    public_key: str
    key_id: str
    created_at: str


@router.get("/{agent_id}", response_model=KeyResponse)
@rate_limit(rate=200, per=60)
async def get_public_key(request: Request, agent_id: str) -> KeyResponse | JSONResponse:
    """Get the registered public key for an agent."""
    import base64
    from datetime import UTC, datetime

    key_data = public_keys.PUBLIC_KEY_REGISTRY.get(agent_id)
    if not key_data:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": f"No public key found for {agent_id}",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    public_key_bytes: bytes = key_data["public_key"]
    return KeyResponse(
        agent_id=agent_id,
        public_key=base64.b64encode(public_key_bytes).decode("utf-8"),
        key_id=key_data.get("key_id", ""),
        created_at=key_data.get("created_at", ""),
    )


@router.post("/register")
@rate_limit(rate=50, per=60)
async def register_public_key(request: Request, req: RegisterKeyRequest) -> dict[str, Any]:
    """Register a public key for an agent."""
    import base64

    try:
        public_key_bytes = base64.b64decode(req.public_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 public_key: {e}") from e

    success = public_keys.register_public_key(req.agent_id, public_key_bytes, req.key_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to register public key")

    logger.info("Public key registered for %s via key exchange endpoint", req.agent_id)
    return {
        "success": True,
        "agent_id": req.agent_id,
        "key_id": req.key_id or public_keys.PUBLIC_KEY_REGISTRY[req.agent_id]["key_id"],
        "message": "Public key registered successfully",
    }
