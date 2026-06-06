"""
WebSocket module for AITBC Agent Coordinator
"""

from .agent_stream import AgentStreamHandler, ConnectionManager, get_connection_manager

__all__ = [
    "AgentStreamHandler",
    "ConnectionManager",
    "get_connection_manager"
]
