"""
WebSocket Router for AITBC Agent Coordinator
Provides WebSocket endpoints for real-time agent messaging and presence tracking
"""

import os
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from aitbc.aitbc_logging import get_logger

from ..websocket import AgentStreamHandler, get_connection_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["websocket"])


def _authenticate_websocket(websocket: WebSocket, token: str | None) -> bool:
    """Authenticate a WebSocket connection via API key or JWT token.

    Accepts either:
    - A raw API key matching COORDINATOR_API_KEY or SECRET_KEY env var
    - A JWT bearer token validated by the auth subsystem

    Returns True if authenticated, False otherwise.
    """
    if not token:
        return False

    # Fast path: check against shared API key env vars (same pattern as coin_requests.py)
    expected_key = os.getenv("COORDINATOR_API_KEY") or os.getenv("SECRET_KEY")
    if expected_key and token == expected_key:
        return True

    # JWT validation via auth subsystem
    try:
        from ..auth.jwt_handler import jwt_handler

        validation = jwt_handler.validate_token(token)
        if validation.get("valid"):
            return True
    except Exception as e:
        logger.warning("WebSocket JWT validation failed: %s", e)

    return False


async def _reject_ws(websocket: WebSocket, reason: str) -> None:
    """Close a WebSocket connection with 401 status before accepting."""
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
    logger.warning("WebSocket connection rejected: %s", reason)


@router.websocket("/messages/stream")
async def websocket_message_stream(
    websocket: WebSocket,
    agent_id: str = Query(..., description="Agent ID"),
    token: str | None = Query(None, description="API key or JWT bearer token for authentication"),
) -> None:
    """WebSocket endpoint for real-time agent messaging with automatic handler triggering.

    v0.6.5: Requires authentication via `token` query parameter (API key or JWT).
    """
    if not _authenticate_websocket(websocket, token):
        await _reject_ws(websocket, "Authentication required")
        return

    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    try:
        await stream_handler.handle_message_stream(websocket, agent_id)
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
    """
    if not _authenticate_websocket(websocket, token):
        await _reject_ws(websocket, "Authentication required")
        return

    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    try:
        await stream_handler.handle_presence_stream(websocket, agent_id)
    except WebSocketDisconnect:
        logger.info("WebSocket presence disconnected for agent %s", agent_id)


@router.get("/ws/status")
async def websocket_status() -> dict[str, Any]:
    """Get WebSocket listener status"""
    connection_manager = get_connection_manager()
    return {
        "active_connections": len(connection_manager.active_connections),
        "connected_agents": list(connection_manager.active_connections.keys()),
        "registered_handlers": list(connection_manager.message_handlers.keys()),
        "queued_messages": {agent_id: len(messages) for agent_id, messages in connection_manager.agent_inboxes.items()},
    }
