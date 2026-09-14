from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.agent_envelope import (
    identity_claim,
    rotation_claim,
    verify_identity_claim,
    verify_rotation_claim,
)
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.rate_limiting import rate_limit

from .. import state
from ..config import settings
from ..models import AgentRegistrationRequest, AgentStatusUpdate, IdentityRotationRequest
from ..routing.agent_discovery import create_agent_info
from ..services.agent_auth import AgentPrincipal, authorize_agent_scope, optional_agent
from ..services.nonce_store import REGISTRATION_NONCE_TTL_SECONDS, get_nonce_store

logger = get_logger(__name__)
router = APIRouter()

# Resolves the caller's principal if credentials are present, ``None``
# otherwise — scope enforcement is flag-driven via agent_msg_signature_mode.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]


def _verify_identity_attestation(request: AgentRegistrationRequest, expected_address: str) -> bool:
    """True iff the request's ``identity_proof`` signs the binding claim with
    the ``expected_address`` key (doc §3 — the key holder alone can bind)."""
    if not (request.identity_address and request.identity_proof and request.identity_nonce and request.registered_at):
        return False
    claim = identity_claim(
        agent_id=request.agent_id,
        identity_address=request.identity_address,
        chain_id=request.chain_id or "",
        nonce=request.identity_nonce,
        registered_at=request.registered_at,
    )
    return verify_identity_claim(claim, request.identity_proof, expected_address)


async def _consume_identity_nonce(agent_id: str, nonce: str | None) -> None:
    """Burn the one-time registration nonce or raise 403."""
    if not nonce or not await get_nonce_store().consume_registration_nonce(agent_id, nonce):
        raise HTTPException(status_code=403, detail="invalid_identity_nonce")


def _reproves_bound_identity(request: AgentRegistrationRequest, bound_address: str) -> bool:
    """True when a re-registration re-proves the already-bound key.

    The claim must name the same canonical address *and* carry a fresh
    ``identity_proof`` from that key — anything else is a hijack attempt.
    """
    same_identity = request.identity_address is not None and canonical_address(request.identity_address) == canonical_address(
        bound_address
    )
    return same_identity and _verify_identity_attestation(request, bound_address)


def _canonical_identity_address(raw: str) -> str:
    """Canonical strict-EVM form, or 422.

    The route's published 422 slot is FastAPI's own validation error, so this
    raise does not need to sit in the handler to be represented there.
    """
    try:
        return canonical_address(raw, strict=True)
    except ValueError:
        raise HTTPException(status_code=422, detail="identity_address is not an EVM address (0x + 40 hex)") from None


def _build_agent_info(request: AgentRegistrationRequest, identity_address: str | None, registered_proof: str | None) -> Any:
    """Assemble the ``AgentInfo`` record for registration (422 on a malformed
    field set — likewise shadowed by the route's own validation entry)."""
    try:
        agent_info = create_agent_info(
            agent_id=request.agent_id,
            agent_type=request.agent_type,
            capabilities=request.capabilities,
            services=request.services,
            endpoints=request.endpoints,
            chain_id=request.chain_id or "",
            island_id=request.island_id or "",
            identity_address=identity_address,
            registered_proof=registered_proof,
        )
        agent_info.metadata = request.metadata
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return agent_info


@router.post("/agents/register")
@rate_limit(rate=50, per=60)
async def register_agent(request_http: Request, request: AgentRegistrationRequest) -> dict[str, Any]:
    """Register a new agent.

    Identity binding (docs/agent-coordinator/agent-signed-envelopes.md §3):
    supplying ``identity_address`` + ``identity_proof`` binds the agent_id to
    that secp256k1 wallet (the escrow payout address). Once bound, a plain
    re-registration must re-prove the *bound* key — anything else is a
    hijack attempt and gets 409; rotation goes through
    ``PUT /v1/agents/{agent_id}/identity``. In ``enforce`` mode the attestation
    is mandatory; in ``advisory``/``disabled`` agents may still register
    unsigned with ``identity_address = null``.
    """
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")

        existing = await state.agent_registry.get_agent_by_id(request.agent_id)
        bound_address = existing.identity_address if existing else None
        identity_address: str | None = None
        registered_proof: str | None = None

        if bound_address is not None:
            if not _reproves_bound_identity(request, bound_address):
                raise HTTPException(
                    status_code=409,
                    detail="agent_id is bound to an identity; re-registration requires identity_proof from the bound key (rotate via PUT /v1/agents/{agent_id}/identity)",
                )
            await _consume_identity_nonce(request.agent_id, request.identity_nonce)
            identity_address = bound_address
            registered_proof = request.identity_proof
        elif request.identity_address is not None:
            identity_address = _canonical_identity_address(request.identity_address)
            if not _verify_identity_attestation(request, identity_address):
                raise HTTPException(status_code=403, detail="invalid_identity_proof")
            await _consume_identity_nonce(request.agent_id, request.identity_nonce)
            registered_proof = request.identity_proof
        elif settings.agent_msg_signature_mode == "enforce":
            raise HTTPException(
                status_code=403,
                detail="identity_address and identity_proof are required when AGENT_MSG_SIGNATURE_MODE=enforce",
            )

        agent_info = _build_agent_info(request, identity_address, registered_proof)
        if not await state.agent_registry.register_agent(agent_info):
            raise HTTPException(status_code=500, detail="Failed to register agent")
        return {
            "status": "success",
            "message": f"Agent {request.agent_id} registered successfully",
            "agent_id": request.agent_id,
            "identity_address": identity_address,
            "registered_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error registering agent: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/agents/discover")
@rate_limit(rate=200, per=60)
async def discover_agents(request: Request, query: dict[str, Any]) -> dict[str, Any]:
    """Discover agents based on criteria"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = await state.agent_registry.discover_agents(query)
        return {
            "status": "success",
            "query": query,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error discovering agents: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# NOTE: this route must stay registered before ``GET /agents/{agent_id}`` —
# Starlette matches in registration order, so ``nonce`` would otherwise be
# captured as an agent_id.
@router.get("/agents/nonce")
@rate_limit(rate=100, per=60)
async def issue_registration_nonce(request: Request, agent_id: str = Query(..., description="Agent ID")) -> dict[str, Any]:
    """Issue a one-time 300s nonce for the registration identity claim (doc §3).

    The response echoes ``chain_id`` so the caller knows which value to put in
    the claim it signs.
    """
    try:
        nonce = await get_nonce_store().issue_registration_nonce(agent_id)
        return {
            "status": "success",
            "agent_id": agent_id,
            "nonce": nonce,
            "chain_id": settings.default_chain_id,
            "expires_in": REGISTRATION_NONCE_TTL_SECONDS,
            "issued_at": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error issuing registration nonce: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/agents/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent(request: Request, agent_id: str) -> dict[str, Any]:
    """Get agent information by ID"""
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agent = await state.agent_registry.get_agent_by_id(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"status": "success", "agent": agent.to_dict(), "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting agent: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/agents/{agent_id}/status")
@rate_limit(rate=50, per=60)
async def update_agent_status(
    request: Request, agent_id: str, request_status: AgentStatusUpdate, principal: OptionalAgent
) -> dict[str, Any]:
    """Update agent status.

    Phase C agent-scoped: ``enforce`` requires a principal bound to
    ``agent_id`` (agent JWT or ``X-Agent-*`` signed headers) or an admin;
    ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_agent_scope(principal, agent_id, "agent_status")
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        from ..routing.agent_discovery import AgentStatus

        success = await state.agent_registry.update_agent_status(
            agent_id, AgentStatus(request_status.status), request_status.load_metrics
        )
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} status updated",
                "agent_id": agent_id,
                "new_status": request_status.status,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update agent status")
    except Exception as e:
        logger.error("Error updating agent status: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


def _canonical_new_address(request: IdentityRotationRequest, old_address: str) -> str:
    """Canonicalize ``request.new_address`` and reject a no-op rotation.

    Both failures are 422s — the route's published 422 slot is FastAPI's own
    validation error, so these raises do not need handler-local source.
    """
    try:
        new_address = canonical_address(request.new_address, strict=True)
    except ValueError:
        raise HTTPException(status_code=422, detail="new_address is not an EVM address (0x + 40 hex)") from None
    if new_address == canonical_address(old_address):
        raise HTTPException(status_code=422, detail="new_address equals the bound identity; re-register instead")
    return new_address


def _parse_rotation_timestamp(rotation_timestamp: str) -> datetime:
    """ISO-8601 parse with naive timestamps treated as UTC; ``ValueError``
    propagates for the route to answer as ``invalid_rotation_timestamp``."""
    rotated_at = datetime.fromisoformat(rotation_timestamp)
    if rotated_at.tzinfo is None:
        rotated_at = rotated_at.replace(tzinfo=UTC)
    return rotated_at


def _rotation_timestamp_stale(rotated_at: datetime) -> bool:
    """The rotation claim's timestamp bounds how long a captured rotation
    stays valid (same skew window as message envelopes)."""
    return abs((datetime.now(UTC) - rotated_at).total_seconds()) > settings.agent_msg_max_skew_seconds


def _new_identity_proof_ok(agent_id: str, agent: Any, request: IdentityRotationRequest, new_address: str) -> bool:
    """``new_proof``: the new key over the registration claim (doc §7)."""
    new_claim = identity_claim(
        agent_id=agent_id,
        identity_address=request.new_address,
        chain_id=request.chain_id or agent.chain_id or "",
        nonce=request.identity_nonce,
        registered_at=request.registered_at,
    )
    return verify_identity_claim(new_claim, request.new_proof, new_address)


def _rotation_proof_ok(agent_id: str, request: IdentityRotationRequest, old_address: str, new_address: str) -> bool:
    """``rotation_proof``: the currently bound key over
    ``{agent_id, old_address, new_address, timestamp}`` (doc §7)."""
    rot_claim = rotation_claim(
        agent_id=agent_id,
        old_address=old_address,
        new_address=request.new_address,
        timestamp=request.rotation_timestamp,
    )
    return verify_rotation_claim(rot_claim, request.rotation_proof, old_address)


async def _rotation_guards(agent_id: str, request: IdentityRotationRequest) -> tuple[Any, str, str]:
    """Every rotation precondition, resolved as a route dependency.

    Written as ``Depends`` rather than called from the handler so the OpenAPI
    error-responses pass — which scans a route's own source *and* its
    dependency callables — keeps publishing these raises.

    Returns ``(agent, old_address, new_address)`` for the handler body.
    """
    if not state.agent_registry:
        raise HTTPException(status_code=503, detail="Agent registry not available")
    agent = await state.agent_registry.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    old_address = agent.identity_address
    if not old_address:
        raise HTTPException(
            status_code=409,
            detail="Agent has no bound identity; bind one via POST /v1/agents/register",
        )
    new_address = _canonical_new_address(request, old_address)

    try:
        rotated_at = _parse_rotation_timestamp(request.rotation_timestamp)
    except ValueError:
        raise HTTPException(status_code=403, detail="invalid_rotation_timestamp") from None
    if _rotation_timestamp_stale(rotated_at):
        raise HTTPException(status_code=403, detail="stale_rotation_timestamp")
    if not _new_identity_proof_ok(agent_id, agent, request, new_address):
        raise HTTPException(status_code=403, detail="invalid_identity_proof")
    if not _rotation_proof_ok(agent_id, request, old_address, new_address):
        raise HTTPException(status_code=403, detail="invalid_rotation_proof")
    return agent, old_address, new_address


ResolvedRotation = Annotated[tuple[Any, str, str], Depends(_rotation_guards)]


@router.put("/agents/{agent_id}/identity")
@rate_limit(rate=50, per=60)
async def rotate_agent_identity(
    request_http: Request, agent_id: str, request: IdentityRotationRequest, rotation: ResolvedRotation
) -> dict[str, Any]:
    """Rotate the identity bound to ``agent_id`` — the doc §7 dual-proof scheme.

    Requires ``new_proof`` (the new key signing the registration claim, over a
    fresh one-time nonce) **and** ``rotation_proof`` (the currently bound key
    signing ``{agent_id, old_address, new_address, timestamp}``). Both must
    verify; old messages keep verifying against their embedded ``signer``.
    """
    agent, old_address, new_address = rotation
    try:
        # _rotation_guards already 503'd on a missing registry — re-narrow for mypy.
        assert state.agent_registry is not None
        await _consume_identity_nonce(agent_id, request.identity_nonce)

        if not await state.agent_registry.update_agent_identity(agent_id, new_address, request.new_proof):
            raise HTTPException(status_code=500, detail="Failed to rotate identity")
        return {
            "status": "success",
            "message": f"Agent {agent_id} identity rotated",
            "agent_id": agent_id,
            "identity_address": new_address,
            "previous_identity_address": old_address,
            "rotated_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error rotating identity for agent %s: %s", agent_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/agents/{agent_id}/heartbeat")
@rate_limit(rate=100, per=60)
async def agent_heartbeat(request: Request, agent_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Receive heartbeat from agent.

    Phase C agent-scoped: ``enforce`` requires a principal bound to
    ``agent_id`` (agent JWT or ``X-Agent-*`` signed headers) or an admin;
    ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_agent_scope(principal, agent_id, "heartbeat")
    try:
        if not state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        from ..routing.agent_discovery import AgentStatus

        success = await state.agent_registry.update_agent_status(agent_id, AgentStatus.ACTIVE, {})
        if success:
            return {
                "status": "success",
                "message": f"Heartbeat received from {agent_id}",
                "agent_id": agent_id,
                "heartbeat_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=404, detail="Agent not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing heartbeat: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
