"""Agent session auth — wallet-login nonce issuance and JWT minting (Phase B1).

``POST /api/v1/agent/auth/nonce`` issues a one-time 300 s nonce;
``POST /api/v1/agent/auth/login`` exchanges a wallet signature over the
``aitbc-agent-login-v1`` claim ``{"agent_id","wallet_address","chain_id","nonce"}``
for a JWT carrying ``agent_id`` + ``wallet`` claims (role ``agent``).

The endpoint authenticates the *binding*, not just the key: the signature must
recover ``wallet_address`` and ``wallet_address`` must equal the registry
``identity_address`` for ``agent_id`` — so the agent must be registered and
identity-bound (``POST /v1/agents/register`` with ``identity_proof``) before it
can log in. This is independent of ``agent_msg_signature_mode``: a login proves
a key the caller either holds or does not, in every mode.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger
from aitbc.auth.jwt import create_access_token
from aitbc.crypto.agent_envelope import login_claim, verify_login_claim
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.rate_limiting import rate_limit

from .. import state
from ..config import settings
from ..services.agent_auth import AgentPrincipal, require_agent
from ..services.nonce_store import LOGIN_NONCE_TTL_SECONDS, get_nonce_store

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent/auth", tags=["agent-auth"])


class AgentLoginRequest(BaseModel):
    """Wallet-login body: the signature covers the canonical login claim."""

    agent_id: str = Field(..., description="Registered, identity-bound agent ID")
    wallet_address: str = Field(..., description="Wallet the signature must recover to")
    nonce: str = Field(..., description="One-time nonce from POST /api/v1/agent/auth/nonce")
    signature: str = Field(..., description="0x-prefixed secp256k1 signature over the login claim")
    chain_id: str | None = Field(None, description="Chain ID covered by the claim (default: coordinator's)")


@router.post("/nonce")
@rate_limit(rate=50, per=60)
async def issue_login_nonce(request: Request, agent_id: str = Query(..., description="Agent ID")) -> dict[str, Any]:
    """Issue a one-time 300 s nonce for the wallet-login claim.

    Echoes ``chain_id`` so the caller signs the same value the coordinator
    rebuilds (same convention as ``GET /v1/agents/nonce``).
    """
    try:
        nonce = await get_nonce_store().issue_login_nonce(agent_id)
        return {
            "status": "success",
            "agent_id": agent_id,
            "nonce": nonce,
            "chain_id": settings.default_chain_id,
            "expires_in": LOGIN_NONCE_TTL_SECONDS,
            "issued_at": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error issuing login nonce: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/login")
@rate_limit(rate=20, per=60)
async def agent_login(request: Request, req: AgentLoginRequest) -> dict[str, Any]:
    """Exchange a wallet signature over the login claim for an agent JWT.

    Checks, in order: agent registered → agent identity-bound → claimed wallet
    equals the bound identity → signature over
    ``{"agent_id","wallet_address","chain_id","nonce"}`` verifies against the
    bound identity → nonce is a live one-time value. The JWT it returns carries
    ``agent_id`` + ``wallet`` claims with role ``agent`` and authenticates
    HTTP endpoints (``Authorization: Bearer``) and WebSocket streams
    (``?token=``).
    """
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agent = await state.agent_registry.get_agent_by_id(req.agent_id)
        if agent is None:
            raise HTTPException(status_code=401, detail="agent_not_registered")
        bound_identity = agent.identity_address
        if not bound_identity:
            raise HTTPException(status_code=401, detail="agent_not_bound")
        try:
            claimed_wallet = canonical_address(req.wallet_address, strict=True)
        except ValueError:
            raise HTTPException(status_code=422, detail="wallet_address is not an EVM address (0x + 40 hex)") from None
        if claimed_wallet != canonical_address(bound_identity):
            raise HTTPException(status_code=401, detail="wallet_mismatch")
        claim = login_claim(
            agent_id=req.agent_id,
            wallet_address=req.wallet_address,
            chain_id=req.chain_id or settings.default_chain_id,
            nonce=req.nonce,
        )
        if not verify_login_claim(claim, req.signature, bound_identity):
            raise HTTPException(status_code=401, detail="invalid_signature")
        # Consumed last so a structurally bad attempt does not burn a live nonce;
        # a replayed login fails here even with an otherwise-valid signature.
        if not await get_nonce_store().consume_login_nonce(req.agent_id, req.nonce):
            raise HTTPException(status_code=401, detail="invalid_nonce")
        token = create_access_token(
            user_id=req.agent_id,
            role="agent",
            extra_claims={"agent_id": req.agent_id, "wallet": claimed_wallet},
        )
        logger.info("Agent %s logged in with wallet %s", req.agent_id, claimed_wallet)
        return {
            "status": "success",
            "access_token": token,
            "token_type": "Bearer",  # nosec B105 — RFC 6750 scheme name, not a secret
            "agent_id": req.agent_id,
            "wallet": claimed_wallet,
            "issued_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during agent login: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/session")
@rate_limit(rate=200, per=60)
async def agent_session(request: Request, principal: Annotated[AgentPrincipal, Depends(require_agent)]) -> dict[str, Any]:
    """Return the authenticated principal — a probe for the Phase B1 credentials."""
    return {
        "status": "success",
        "agent_id": principal.agent_id,
        "wallet": principal.wallet,
        "auth_type": principal.auth_type,
        "is_admin": principal.is_admin,
        "timestamp": datetime.now(UTC).isoformat(),
    }
