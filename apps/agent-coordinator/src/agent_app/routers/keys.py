"""Public key exchange endpoints for the Agent Coordinator."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..config import settings
from ..encryption import public_keys
from ..services.agent_auth import AgentPrincipal, authorize_agent_scope, optional_agent

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agent/keys", tags=["agent-keys"])

# Resolves the caller's principal if credentials are present, ``None``
# otherwise — scope enforcement is flag-driven via agent_msg_signature_mode.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]


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
async def register_public_key(request: Request, req: RegisterKeyRequest, principal: OptionalAgent) -> dict[str, Any]:
    """Register a public key for an agent.

    Phase C agent-scoped: ``enforce`` requires a principal bound to
    ``req.agent_id`` (agent JWT or ``X-Agent-*`` signed headers) or an admin,
    and a non-admin principal must carry an ``identity_address`` binding — the
    registered key is then stamped with the principal's bound identity so the
    record shows which wallet authorized it. ``advisory`` logs and allows;
    ``disabled`` is a no-op.
    """
    authorize_agent_scope(principal, req.agent_id, "keys_register")
    if (
        settings.agent_msg_signature_mode == "enforce"
        and principal is not None
        and not principal.is_admin
        and not principal.wallet
    ):
        # A principal with no bound identity (a bare user JWT) cannot authorise
        # an agent's key registration — the binding is what ties key to wallet.
        raise HTTPException(status_code=403, detail="agent_identity_required")

    import base64

    try:
        public_key_bytes = base64.b64decode(req.public_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 public_key: {e}") from e

    identity_address = principal.wallet if principal is not None and not principal.is_admin else None
    success = public_keys.register_public_key(req.agent_id, public_key_bytes, req.key_id, identity_address=identity_address)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to register public key")

    logger.info("Public key registered for %s via key exchange endpoint", req.agent_id)
    return {
        "success": True,
        "agent_id": req.agent_id,
        "key_id": req.key_id or public_keys.PUBLIC_KEY_REGISTRY[req.agent_id]["key_id"],
        "message": "Public key registered successfully",
    }
