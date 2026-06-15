"""
WebSocket Router for AITBC Agent Coordinator
Provides WebSocket endpoints for real-time agent messaging and presence tracking
"""

from typing import Any

from fastapi import APIRouter, Query, WebSocket

from aitbc import get_logger

from ..websocket import AgentStreamHandler, get_connection_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["websocket"])


@router.websocket("/messages/stream")
async def websocket_message_stream(websocket: WebSocket, agent_id: str = Query(..., description="Agent ID")) -> None:
    """WebSocket endpoint for real-time agent messaging with automatic handler triggering"""
    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    await stream_handler.handle_message_stream(websocket, agent_id)


@router.websocket("/presence/stream")
async def websocket_presence_stream(websocket: WebSocket, agent_id: str = Query(..., description="Agent ID")) -> None:
    """WebSocket endpoint for real-time agent presence tracking"""
    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    await stream_handler.handle_presence_stream(websocket, agent_id)


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
