"""
WebSocket Router for AITBC Agent Coordinator
Provides WebSocket endpoints for real-time agent messaging and presence tracking
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from aitbc import get_logger

from ..websocket import AgentStreamHandler, get_connection_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["websocket"])


@router.websocket("/messages/stream")
async def websocket_message_stream(
    websocket: WebSocket,
    agent_id: str = Query(..., description="Agent ID")
):
    """WebSocket endpoint for real-time agent messaging"""
    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    await stream_handler.handle_message_stream(websocket, agent_id)


@router.websocket("/presence/stream")
async def websocket_presence_stream(
    websocket: WebSocket,
    agent_id: str = Query(..., description="Agent ID")
):
    """WebSocket endpoint for real-time agent presence tracking"""
    connection_manager = get_connection_manager()
    stream_handler = AgentStreamHandler(connection_manager)

    await stream_handler.handle_presence_stream(websocket, agent_id)
