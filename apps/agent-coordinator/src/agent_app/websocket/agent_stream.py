"""
WebSocket streaming for real-time agent messaging
Provides real-time message delivery and presence tracking
Includes automatic handler triggering for PING, REQUEST_COINS, etc.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from ..services.agent_auth import AgentPrincipal

from aitbc.aitbc_logging import get_logger
from aitbc.crypto import TransactionService  # noqa: F401 - re-exported; coin-grant tests patch agent_stream.TransactionService

logger = get_logger(__name__)

# Expected failure surface for the best-effort handlers below: filesystem/OS
# and sqlite ledger errors, JSON/request decode (ValueError/TypeError/
# KeyError/AttributeError), lazy backend imports, websocket RuntimeErrors,
# and outbound HTTP (httpx). Genuine BaseExceptions (incl.
# asyncio.CancelledError) still propagate (#1865).
_OPS_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    RuntimeError,
    sqlite3.Error,
    httpx.HTTPError,
)


def _get_approval_strategy():
    """Get the configured approval strategy (v0.5.9 §3).

    Returns the strategy instance based on COIN_APPROVAL_MODE env var.
    Moved from hermes_service.handlers.request_coins_handler.
    """
    from ..services.approval import AIApprovalStrategy, AutomaticApprovalStrategy, ManualApprovalStrategy

    coordinator_url = os.getenv("AGENT_COORDINATOR_URL", os.getenv("HERMES_COORDINATOR_URL", "http://localhost:8107"))
    agent_id = os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator"))
    approval_mode = os.getenv("COIN_APPROVAL_MODE", "manual").lower()
    if approval_mode == "automatic":
        return AutomaticApprovalStrategy(coordinator_url, agent_id), approval_mode
    elif approval_mode == "ai":
        return AIApprovalStrategy(coordinator_url, agent_id), approval_mode
    else:
        return ManualApprovalStrategy(coordinator_url, agent_id), approval_mode


class ConnectionManager:
    """Manages WebSocket connections for agents"""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.topic_subscriptions: dict[str, set[str]] = {}
        self.agent_topics: dict[str, set[str]] = {}
        self.message_handlers: dict[str, list[Callable[[dict[str, Any], ConnectionManager, WebSocket], Any]]] = {}
        self.agent_inboxes: dict[str, list[dict[str, Any]]] = {}
        self.message_storage: Any | None = None
        # v2.0 B1: the principal each connection authenticated as (auth_type only —
        # the credential itself is never stored).
        self.connection_auth: dict[str, str] = {}
        # Phase C: the principal's registry-bound wallet per connection — a
        # public identity address, not a credential. ``request_coins_handler``
        # binds the payout destination to it in enforce mode.
        self.connection_wallets: dict[str, str] = {}

    async def connect(self, websocket: WebSocket, agent_id: str, principal: AgentPrincipal | None = None) -> None:
        """Accept a WebSocket connection from an agent."""
        if agent_id in self.active_connections:
            # Close any stale connection with the same agent_id before replacing it,
            # so the socket does not remain half-open and the old task can exit cleanly.
            old_websocket = self.active_connections[agent_id]
            try:
                await old_websocket.close()
            except _OPS_ERRORS as e:
                logger.warning("Error closing old WebSocket for %s: %s", agent_id, e)
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        self.agent_topics[agent_id] = set()
        self.agent_inboxes[agent_id] = []
        if principal is not None:
            self.connection_auth[agent_id] = principal.auth_type
            if principal.wallet:
                self.connection_wallets[agent_id] = principal.wallet
            else:
                self.connection_wallets.pop(agent_id, None)
            logger.info(
                "Agent %s connected via WebSocket (principal=%s auth_type=%s)",
                agent_id,
                principal.agent_id,
                principal.auth_type,
            )
        else:
            self.connection_auth.pop(agent_id, None)
            self.connection_wallets.pop(agent_id, None)
            logger.info("Agent %s connected via WebSocket", agent_id)
        await websocket.send_json(
            {
                "type": "connection_established",
                "agent_id": agent_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "message": "WebSocket listener active - handlers will be triggered in real-time",
            }
        )
        await self._load_subscriptions(agent_id)

    async def _load_subscriptions(self, agent_id: str) -> None:
        """Restore persisted topic subscriptions when an agent connects."""
        if not self.message_storage:
            return
        try:
            subscriptions = await self.message_storage.get_subscriptions(agent_id)
            for sub in subscriptions:
                topic = sub.get("topic")
                if topic:
                    self.subscribe(agent_id, topic)  # noqa: unawaited-async — sync method
                    logger.info("Restored subscription %s for %s", topic, agent_id)
        except _OPS_ERRORS as e:
            logger.warning("Could not load subscriptions for %s: %s", agent_id, e)

    async def disconnect(self, agent_id: str) -> None:
        """Remove agent connection and close the underlying WebSocket."""
        if agent_id in self.active_connections:
            websocket = self.active_connections[agent_id]
            try:
                await websocket.close()
            except _OPS_ERRORS as e:
                logger.warning("Error closing WebSocket for %s: %s", agent_id, e)
            del self.active_connections[agent_id]
        if agent_id in self.agent_topics:
            for topic in self.agent_topics[agent_id]:
                if topic in self.topic_subscriptions:
                    self.topic_subscriptions[topic].discard(agent_id)
            del self.agent_topics[agent_id]
        self.agent_inboxes.pop(agent_id, None)
        self.connection_auth.pop(agent_id, None)
        self.connection_wallets.pop(agent_id, None)
        logger.info("Agent %s disconnected from WebSocket", agent_id)

    async def send_personal_message(self, message: dict[str, Any], agent_id: str) -> bool:
        """Send a message to a specific agent"""
        if agent_id in self.active_connections:
            try:
                websocket = self.active_connections[agent_id]
                await websocket.send_json(message)
                return True
            except _OPS_ERRORS as e:
                logger.error("Error sending message to %s: %s", agent_id, e)
                await self.disconnect(agent_id)
                return False
        return False

    async def broadcast(self, message: dict[str, Any], topic: str | None = None) -> None:
        """Broadcast message to all agents or topic subscribers"""
        if topic:
            recipients = self.topic_subscriptions.get(topic, set())
        else:
            recipients = set(self.active_connections.keys())
        for agent_id in recipients:
            if agent_id in self.active_connections:
                await self.send_personal_message(message, agent_id)
        logger.info("Broadcast message to %s agents (topic: %s)", len(recipients), topic)

    def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribe agent to topic"""
        if agent_id not in self.agent_topics:
            self.agent_topics[agent_id] = set()
        if topic not in self.topic_subscriptions:
            self.topic_subscriptions[topic] = set()
        self.agent_topics[agent_id].add(topic)
        self.topic_subscriptions[topic].add(agent_id)
        logger.info("Agent %s subscribed to topic %s", agent_id, topic)

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe agent from topic"""
        if agent_id in self.agent_topics:
            self.agent_topics[agent_id].discard(topic)
        if topic in self.topic_subscriptions:
            self.topic_subscriptions[topic].discard(agent_id)
        logger.info("Agent %s unsubscribed from topic %s", agent_id, topic)

    def get_connected_agents(self) -> list[str]:
        """Get list of connected agent IDs"""
        return list(self.active_connections.keys())

    def get_topic_subscribers(self, topic: str) -> set[str]:
        """Get subscribers for a topic"""
        return self.topic_subscriptions.get(topic, set())

    def register_handler(
        self, message_type: str, handler: Callable[[dict[str, Any], ConnectionManager, WebSocket], Any]
    ) -> None:
        """Register a message handler for specific message type"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
        logger.info("Registered handler for message type: %s", message_type)

    async def trigger_handlers(self, message: dict[str, Any], websocket: WebSocket) -> dict[str, Any]:
        """Trigger all registered handlers for the message type"""
        content = message.get("content", "")
        message_type = "unknown"
        if "PING" in content.upper():
            message_type = "PING"
        elif "REQUEST_COINS" in content.upper():
            message_type = "REQUEST_COINS"
        elif "HELLO" in content.upper():
            message_type = "HELLO"
        handlers = self.message_handlers.get(message_type, [])
        results = []
        for handler in handlers:
            try:
                result = await handler(message, self, websocket)
                results.append({"handler": handler.__name__, "result": result, "success": True})
            except _OPS_ERRORS as e:
                logger.error("Handler error: %s", e)
                results.append({"handler": handler.__name__, "error": str(e), "success": False})
        return {"message_type": message_type, "handlers_triggered": len(handlers), "results": results}

    async def deliver_queued_messages(self, agent_id: str) -> None:
        """Deliver queued messages when agent connects"""
        if agent_id in self.agent_inboxes and self.agent_inboxes[agent_id]:
            queued_messages = self.agent_inboxes[agent_id].copy()
            self.agent_inboxes[agent_id].clear()
            for message in queued_messages:
                await self.send_personal_message(message, agent_id)
            logger.info("Delivered %s queued messages to %s", len(queued_messages), agent_id)


class AgentStreamHandler:
    """WebSocket handler for agent message streaming"""

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self.connection_manager = connection_manager

    async def handle_message_stream(
        self, websocket: WebSocket, agent_id: str, principal: AgentPrincipal | None = None
    ) -> None:
        """Handle WebSocket message stream for an agent"""
        await self.connection_manager.connect(websocket, agent_id, principal)
        await self.connection_manager.deliver_queued_messages(agent_id)
        try:
            while True:
                data = await websocket.receive_json()
                await self._dispatch_stream_message(websocket, agent_id, data)
        except WebSocketDisconnect:
            pass
        except _OPS_ERRORS as e:
            logger.error("Error in message stream for %s: %s", agent_id, e)
        finally:
            # Runs on every exit path — an unexpected error propagates after
            # cleanup instead of leaving a stale entry in active_connections.
            await self.connection_manager.disconnect(agent_id)

    async def _dispatch_stream_message(self, websocket: WebSocket, agent_id: str, data: dict[str, Any]) -> None:
        """Handle one inbound stream message for ``agent_id``.

        Dispatches on ``data["type"]``: subscribe/unsubscribe update the
        topic maps and ack; ``message`` triggers handlers, acks, and forwards
        to the recipient; ``broadcast`` fans out to the topic; ``heartbeat``
        acks; anything else logs a warning.
        """
        message_type = data.get("type", "message")
        payload = data.get("payload", {})
        if message_type == "subscribe":
            topic = payload.get("topic")
            if topic:
                self.connection_manager.subscribe(agent_id, topic)  # noqa: unawaited-async — sync method
                await websocket.send_json(
                    {"type": "subscription_confirmed", "topic": topic, "timestamp": datetime.now(UTC).isoformat()}
                )
        elif message_type == "unsubscribe":
            topic = payload.get("topic")
            if topic:
                self.connection_manager.unsubscribe(agent_id, topic)  # noqa: unawaited-async — sync method
                await websocket.send_json(
                    {"type": "unsubscription_confirmed", "topic": topic, "timestamp": datetime.now(UTC).isoformat()}
                )
        elif message_type == "message":
            message_data = {
                "sender_id": agent_id,
                "content": payload.get("content", ""),
                "recipient_id": payload.get("recipient_id"),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            handler_results = await self.connection_manager.trigger_handlers(message_data, websocket)
            await websocket.send_json(
                {
                    "type": "handler_acknowledgment",
                    "message_id": data.get("id"),
                    "handler_results": handler_results,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            recipient_id = payload.get("recipient_id")
            if recipient_id:
                forward_data = {
                    "type": "message",
                    "sender_id": agent_id,
                    "recipient_id": recipient_id,
                    "content": payload.get("content"),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await self.connection_manager.send_personal_message(forward_data, recipient_id)
        elif message_type == "broadcast":
            topic = payload.get("topic")
            broadcast_data = {
                "type": "broadcast",
                "sender_id": agent_id,
                "content": payload.get("content"),
                "topic": topic,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await self.connection_manager.broadcast(broadcast_data, topic)
        elif message_type == "heartbeat":
            await websocket.send_json({"type": "heartbeat_ack", "timestamp": datetime.now(UTC).isoformat()})
        else:
            logger.warning("Unknown message type: %s", message_type)

    async def handle_presence_stream(
        self, websocket: WebSocket, agent_id: str, principal: AgentPrincipal | None = None
    ) -> None:
        """Handle WebSocket presence stream for an agent"""
        await self.connection_manager.connect(websocket, agent_id, principal)
        try:
            await websocket.send_json(
                {
                    "type": "presence_update",
                    "agent_id": agent_id,
                    "status": "online",
                    "connected_agents": self.connection_manager.get_connected_agents(),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            while True:
                data = await websocket.receive_json()
                message_type = data.get("type", "presence")
                if message_type == "presence":
                    presence_data = {
                        "type": "presence_update",
                        "agent_id": agent_id,
                        "status": data.get("status", "online"),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                    await self.connection_manager.broadcast(presence_data)
                elif message_type == "get_agents":
                    await websocket.send_json(
                        {
                            "type": "agents_list",
                            "agents": self.connection_manager.get_connected_agents(),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                elif message_type == "heartbeat":
                    await websocket.send_json({"type": "heartbeat_ack", "timestamp": datetime.now(UTC).isoformat()})
        except WebSocketDisconnect:
            await self.connection_manager.disconnect(agent_id)
            offline_data = {
                "type": "presence_update",
                "agent_id": agent_id,
                "status": "offline",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await self.connection_manager.broadcast(offline_data)
        except _OPS_ERRORS as e:
            logger.error("Error in presence stream for %s: %s", agent_id, e)
        finally:
            # Idempotent — also covers unexpected errors that propagate.
            await self.connection_manager.disconnect(agent_id)


_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get global connection manager"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
        _register_builtin_handlers(_connection_manager)
    return _connection_manager


async def ping_handler(message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket) -> dict[str, Any]:
    """Handle PING messages with automatic PONG response"""
    sender = message.get("sender_id", "unknown")
    recipient = message.get("recipient_id", "unknown")
    logger.info("PING received from %s, triggering PONG", sender)
    pong_message = {
        "type": "PONG",
        "sender": recipient,
        "recipient": sender,
        "content": f"PONG from {recipient}",
        "timestamp": datetime.now(UTC).isoformat(),
        "original_message_id": message.get("id"),
    }
    await connection_manager.send_personal_message(pong_message, sender)
    return {"action": "pong_sent", "recipient": sender, "original_ping": message.get("id")}


def hello_handler(message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket) -> dict[str, Any]:
    """Handle HELLO messages"""
    sender = message.get("sender_id", "unknown")
    logger.info("HELLO received from %s", sender)
    return {"action": "hello_acknowledged", "sender": sender}


from .agent_stream_coins import (  # noqa: F401 - re-exported; coin-grant tests drive agent_stream.<name>
    INITIAL_COIN_AMOUNT,
    TRANSACTION_FEE,
    _AGENT_DB_SCHEMA,
    _AGENT_DB_COMPAT_COLUMNS,
    _AGENT_DB_OPEN_ATTEMPTS,
    _has_received_initial_coins,
    _submit_transaction,
    _ensure_agent_db_columns,
    _agent_db_conn,
    _record_coin_request,
    _record_claiming_coin_request,
    _claim_budget_gate,
    _budgeted_claim_coin_request,
    _finish_claimed_coin_request,
    _record_pending_coin_request,
    _wallet_match,
    _parse_coin_request,
    _pending_coin_response,
    _wallet_mismatch_response,
    _sign_submit_claim,
    _grant_confirmation,
    _repeat_coin_request,
    _first_coin_request,
    request_coins_handler,
)


def _register_builtin_handlers(connection_manager: ConnectionManager) -> None:
    """Register built-in message handlers"""
    connection_manager.register_handler("PING", ping_handler)
    connection_manager.register_handler("HELLO", hello_handler)
    connection_manager.register_handler("REQUEST_COINS", request_coins_handler)
    logger.info("Built-in handlers registered: PING, HELLO, REQUEST_COINS")
