"""
WebSocket Router for AITBC Agent Coordinator
Provides WebSocket endpoints for real-time agent messaging and presence tracking
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from aitbc.aitbc_logging import get_logger

from ..config import settings
from ..services.agent_auth import AgentPrincipal, require_agent, resolve_ws_principal, shared_key_principal
from ..websocket import AgentStreamHandler, get_connection_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["websocket"])


def _authenticate_websocket(websocket: WebSocket | None, token: str | None) -> bool:
    """Synchronous "is this credential valid" check — the v0.6.5 contract.

    Kept for callers that only need validity, not identity (the follower-key
    scope tests pin this exact signature). The endpoints themselves use
    :func:`resolve_ws_principal`, which additionally yields the principal the
    ``agent_id`` query param is bound to.
    """
    if shared_key_principal(token) is not None:
        return True
    if not token:
        return False
    try:
        from aitbc.auth import get_jwt_handler

        return bool(get_jwt_handler().validate_token(token).get("valid"))
    except Exception as e:
        logger.warning("WebSocket JWT validation failed: %s", e)
        return False


async def _reject_ws(websocket: WebSocket, reason: str) -> None:
    """Close a WebSocket connection with 401 status before accepting."""
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
    logger.warning("WebSocket connection rejected: %s", reason)


async def _bind_ws_principal(websocket: WebSocket, agent_id: str, principal: AgentPrincipal) -> bool:
    """Check the ``agent_id`` query param against the token-resolved principal.

    ``enforce`` rejects a mismatch outright (the stream is the agent's
    authenticated channel). ``advisory`` logs ``ws_binding_mismatch`` and
    allows — the deployed default stays non-breaking. ``disabled`` skips the
    check entirely. The operator/shared-key principal (``hub-coordinator``) is
    bound like any other: in enforce it may only open hub-coordinator's own
    streams — other agents must connect with their own login JWT.
    """
    if principal.agent_id == agent_id:
        return True
    mode = settings.agent_msg_signature_mode
    if mode == "enforce":
        await _reject_ws(websocket, "agent_id does not match the authenticated principal")
        return False
    if mode == "advisory":
        logger.warning(
            "ws_binding_mismatch agent_id=%s principal=%s auth_type=%s",
            agent_id,
            principal.agent_id,
            principal.auth_type,
        )
    return True


@router.websocket("/messages/stream")
async def websocket_message_stream(
    websocket: WebSocket,
    agent_id: str = Query(..., description="Agent ID"),
    token: str | None = Query(None, description="API key or JWT bearer token for authentication"),
) -> None:
    """WebSocket endpoint for real-time agent messaging with automatic handler triggering.

    v0.6.5: Requires authentication via `token` query parameter (API key or JWT).
    v2.0 B1: the token resolves to a principal; in enforce mode ``agent_id``
    must equal it (shared key → ``hub-coordinator``, JWT → ``agent_id`` claim).
    """
    principal = await resolve_ws_principal(token)
    if principal is None:
        await _reject_ws(websocket, "Authentication required")
        return
    if not await _bind_ws_principal(websocket, agent_id, principal):
        return

    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    try:
        await stream_handler.handle_message_stream(websocket, agent_id, principal)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for agent %s", agent_id)


@router.websocket("/presence/stream")
async def websocket_presence_stream(
    websocket: WebSocket,
    agent_id: str = Query(..., description="Agent ID"),
    token: str | None = Query(None, description="API key or JWT bearer token for authentication"),
) -> None:
    """WebSocket endpoint for real-time agent presence tracking.

    v0.6.5: Requires authentication via `token` query parameter (API key or JWT).
    v2.0 B1: ``agent_id`` is bound to the token's principal like /messages/stream.
    """
    principal = await resolve_ws_principal(token)
    if principal is None:
        await _reject_ws(websocket, "Authentication required")
        return
    if not await _bind_ws_principal(websocket, agent_id, principal):
        return

    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    try:
        await stream_handler.handle_presence_stream(websocket, agent_id, principal)
    except WebSocketDisconnect:
        logger.info("WebSocket presence disconnected for agent %s", agent_id)


@router.get("/ws/status")
async def websocket_status(principal: Annotated[AgentPrincipal, Depends(require_agent)]) -> dict[str, Any]:
    """Get WebSocket listener status.

    v2.0 B1: requires any valid principal — agent JWT, signed ``X-Agent-*``
    headers, the shared operator key (``X-Api-Key``/``?token=``/Bearer), or an
    admin/operator JWT — in every signature mode.
    """
    connection_manager = get_connection_manager()
    return {
        "active_connections": len(connection_manager.active_connections),
        "connected_agents": list(connection_manager.active_connections.keys()),
        "registered_handlers": list(connection_manager.message_handlers.keys()),
        "queued_messages": {agent_id: len(messages) for agent_id, messages in connection_manager.agent_inboxes.items()},
        "authenticated_as": principal.agent_id,
        "auth_type": principal.auth_type,
    }
