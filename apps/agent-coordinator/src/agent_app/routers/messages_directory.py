"""Agent directory/ops routes split from ``messages.py`` (#1860 Phase 6).

Load-balancer stats/strategy, registry stats, agents-by-service/capability
lookups and the peer-connection routes moved here byte-identical (modulo
the ``state.`` -> ``_messages.state.`` routing noted below). They are
served on the same ``/api/v1/agent/messages`` prefix via
``messages.router.include_router`` at the position the block originally
occupied, so the route table and OpenAPI surface are unchanged.

``state`` is patched on the ``agent_app.routers.messages`` module object by
tests (``monkeypatch.setattr(messages_router, "state", fake)``), so the moved
endpoints read it through ``_messages.state`` — the same module-object
routing the state-transition mixins use — keeping the monkeypatch seam.
``_OPS_ERRORS`` and ``OptionalAgent`` are imported from ``messages``;
import ``agent_app.routers.messages`` first (it wires this router in).
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..routing.load_balancer import LoadBalancingStrategy
from ..services.agent_auth import authorize_admin_scope, authorize_any_principal
from . import messages as _messages
from .messages import _OPS_ERRORS, OptionalAgent

logger = get_logger(__name__)

# No prefix or tags here: ``messages.router.include_router`` applies the
# parent's ``/api/v1/agent/messages`` prefix and ``agent-messaging`` tag, so
# paths and tags stay exactly as before.
router = APIRouter()


@router.get("/load-balancer/stats")
@rate_limit(rate=200, per=60)
def get_load_balancer_stats(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get load balancer statistics.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "load_balancer_stats")
    try:
        if not _messages.state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        stats = _messages.state.load_balancer.get_load_balancing_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error getting load balancer stats: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/registry/stats")
@rate_limit(rate=200, per=60)
def get_registry_stats(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get agent registry statistics.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "registry_stats")
    try:
        if not _messages.state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        stats = _messages.state.agent_registry.get_registry_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error getting registry stats: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/agents/service/{service}")
@rate_limit(rate=200, per=60)
def get_agents_by_service(
    request: Request,
    principal: OptionalAgent,
    service: str,
) -> dict[str, Any]:
    authorize_any_principal(principal, "messages_agents_by_service")
    """Get agents that provide a specific service"""
    try:
        if not _messages.state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = _messages.state.agent_registry.get_agents_by_service(service)
        return {
            "status": "success",
            "service": service,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error getting agents by service: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/agents/capability/{capability}")
@rate_limit(rate=200, per=60)
def get_agents_by_capability(
    request: Request,
    principal: OptionalAgent,
    capability: str,
) -> dict[str, Any]:
    authorize_any_principal(principal, "messages_agents_by_capability")
    """Get agents that have a specific capability"""
    try:
        if not _messages.state.agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        agents = _messages.state.agent_registry.get_agents_by_capability(capability)
        return {
            "status": "success",
            "capability": capability,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error getting agents by capability: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/load-balancer/strategy")
@rate_limit(rate=50, per=60)
def set_load_balancing_strategy(
    request: Request, principal: OptionalAgent, strategy: str = Query(..., description="Load balancing strategy")
) -> dict[str, Any]:
    """Set load balancing strategy.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "load_balancer_strategy")
    try:
        if not _messages.state.load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        try:
            load_balancing_strategy = LoadBalancingStrategy(strategy.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}") from None
        _messages.state.load_balancer.set_strategy(load_balancing_strategy)
        return {
            "status": "success",
            "message": f"Load balancing strategy set to {strategy}",
            "strategy": strategy,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error setting load balancing strategy: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/peers/add")
@rate_limit(rate=50, per=60)
async def add_peer(
    request: Request,
    principal: OptionalAgent,
    agent_id: str = Query(..., description="Agent ID"),
    peer_id: str = Query(..., description="Peer agent ID"),
) -> dict[str, Any]:
    """Add a peer connection for an agent.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_add")
    try:
        if not _messages.state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        success = await _messages.state.peer_storage.add_peer(
            agent_id, peer_id, {"connected_at": datetime.now(UTC).isoformat()}
        )
        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} added for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "connected_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add peer")
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error adding peer: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/peers/remove")
@rate_limit(rate=50, per=60)
async def remove_peer(
    request: Request,
    principal: OptionalAgent,
    agent_id: str = Query(..., description="Agent ID"),
    peer_id: str = Query(..., description="Peer agent ID"),
) -> dict[str, Any]:
    """Remove a peer connection for an agent.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_remove")
    try:
        if not _messages.state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        success = await _messages.state.peer_storage.remove_peer(agent_id, peer_id)
        if success:
            return {
                "status": "success",
                "message": f"Peer {peer_id} removed for agent {agent_id}",
                "agent_id": agent_id,
                "peer_id": peer_id,
                "removed_at": datetime.now(UTC).isoformat(),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to remove peer")
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error removing peer: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/peers/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_peers(request: Request, agent_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Get all peers for a specific agent.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_get")
    try:
        if not _messages.state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        peers = await _messages.state.peer_storage.get_agent_peers(agent_id)
        return {
            "status": "success",
            "agent_id": agent_id,
            "peers": peers,
            "count": len(peers),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error retrieving peers for agent %s: %s", agent_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/peers")
@rate_limit(rate=200, per=60)
async def get_all_peers(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Get all peer connections in the system.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "peers_list")
    try:
        if not _messages.state.peer_storage:
            raise HTTPException(status_code=503, detail="Peer storage not available")
        connections = await _messages.state.peer_storage.get_all_peer_connections()
        total_peers = sum(len(peers) for peers in connections.values())
        return {
            "status": "success",
            "connections": connections,
            "total_agents": len(connections),
            "total_peers": total_peers,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error("Error retrieving all peer connections: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
