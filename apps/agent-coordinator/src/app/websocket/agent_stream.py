"""
WebSocket streaming for real-time agent messaging
Provides real-time message delivery and presence tracking
Includes automatic handler triggering for PING, REQUEST_COINS, etc.
"""

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from aitbc.aitbc_logging import get_logger
from aitbc.crypto import TransactionService

logger = get_logger(__name__)


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

    async def connect(self, websocket: WebSocket, agent_id: str) -> None:
        """Accept a WebSocket connection from an agent"""
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        self.agent_topics[agent_id] = set()
        self.agent_inboxes[agent_id] = []
        logger.info("Agent %s connected via WebSocket", agent_id)
        await websocket.send_json(
            {
                "type": "connection_established",
                "agent_id": agent_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "message": "WebSocket listener active - handlers will be triggered in real-time",
            }
        )

    def disconnect(self, agent_id: str) -> None:
        """Remove agent connection"""
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
        if agent_id in self.agent_topics:
            for topic in self.agent_topics[agent_id]:
                if topic in self.topic_subscriptions:
                    self.topic_subscriptions[topic].discard(agent_id)
            del self.agent_topics[agent_id]
        logger.info("Agent %s disconnected from WebSocket", agent_id)

    async def send_personal_message(self, message: dict[str, Any], agent_id: str) -> bool:
        """Send a message to a specific agent"""
        if agent_id in self.active_connections:
            try:
                websocket = self.active_connections[agent_id]
                await websocket.send_json(message)
                return True
            except Exception as e:
                logger.error("Error sending message to %s: %s", agent_id, e)
                self.disconnect(agent_id)
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

    async def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribe agent to topic"""
        if agent_id not in self.agent_topics:
            self.agent_topics[agent_id] = set()
        if topic not in self.topic_subscriptions:
            self.topic_subscriptions[topic] = set()
        self.agent_topics[agent_id].add(topic)
        self.topic_subscriptions[topic].add(agent_id)
        logger.info("Agent %s subscribed to topic %s", agent_id, topic)

    async def unsubscribe(self, agent_id: str, topic: str) -> None:
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
        self, message_type: str, handler: Callable[[dict[str, Any], "ConnectionManager", WebSocket], Any]
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
            except Exception as e:
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

    async def handle_message_stream(self, websocket: WebSocket, agent_id: str) -> None:
        """Handle WebSocket message stream for an agent"""
        await self.connection_manager.connect(websocket, agent_id)
        await self.connection_manager.deliver_queued_messages(agent_id)
        try:
            while True:
                data = await websocket.receive_json()
                message_type = data.get("type", "message")
                payload = data.get("payload", {})
                if message_type == "subscribe":
                    topic = payload.get("topic")
                    if topic:
                        await self.connection_manager.subscribe(agent_id, topic)
                        await websocket.send_json(
                            {"type": "subscription_confirmed", "topic": topic, "timestamp": datetime.now(UTC).isoformat()}
                        )
                elif message_type == "unsubscribe":
                    topic = payload.get("topic")
                    if topic:
                        await self.connection_manager.unsubscribe(agent_id, topic)
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
        except WebSocketDisconnect:
            self.connection_manager.disconnect(agent_id)
        except Exception as e:
            logger.error("Error in message stream for %s: %s", agent_id, e)
            self.connection_manager.disconnect(agent_id)

    async def handle_presence_stream(self, websocket: WebSocket, agent_id: str) -> None:
        """Handle WebSocket presence stream for an agent"""
        await self.connection_manager.connect(websocket, agent_id)
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
            self.connection_manager.disconnect(agent_id)
            offline_data = {
                "type": "presence_update",
                "agent_id": agent_id,
                "status": "offline",
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await self.connection_manager.broadcast(offline_data)
        except Exception as e:
            logger.error("Error in presence stream for %s: %s", agent_id, e)
            self.connection_manager.disconnect(agent_id)


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


async def hello_handler(
    message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket
) -> dict[str, Any]:
    """Handle HELLO messages"""
    sender = message.get("sender_id", "unknown")
    logger.info("HELLO received from %s", sender)
    return {"action": "hello_acknowledged", "sender": sender}


# ── Coin transfer constants ──────────────────────────────────
INITIAL_COIN_AMOUNT = 360000  # AIT granted automatically on first request per node (100 AIT = 360000 seconds)
TRANSACTION_FEE = 36  # blockchain transaction fee (matches RPC default, 0.01 AIT = 36 seconds)


def _has_received_initial_coins(sender: str) -> bool:
    """Check if a sender has already received initial coins.

    Queries the agent coin_requests SQLite database for any prior
    approved/executed request from this sender.
    """
    db_path = os.getenv("AGENT_DB_PATH", os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/agent_coin_requests.db"))
    if not os.path.exists(db_path):
        return False
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM coin_requests WHERE sender = ? AND status IN ('APPROVED') AND transaction_hash IS NOT NULL",
            (sender,),
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.warning("Could not query coin_requests DB: %s", e)
        return False


def _submit_transaction(transaction: dict[str, Any]) -> dict[str, Any] | None:
    """Submit a signed transaction to the blockchain RPC."""
    try:
        rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")
        import httpx

        # Ensure chain_id is present in the transaction body
        if "chain_id" not in transaction or not transaction.get("chain_id"):
            transaction["chain_id"] = os.getenv("CHAIN_ID", "")

        resp = httpx.post(f"{rpc_url}/rpc/transaction", json=transaction, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        logger.info("Transaction submitted: %s", result)
        return result
    except Exception as e:
        logger.error("Failed to submit transaction: %s", e)
        return None


def _record_coin_request(sender: str, amount: int, wallet_address: str, tx_hash: str) -> None:
    """Record the auto-approved coin request in the agent SQLite database."""
    db_path = os.getenv("AGENT_DB_PATH", os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/agent_coin_requests.db"))
    if not os.path.exists(db_path):
        logger.warning("Agent DB not found at %s — skipping record", db_path)
        return
    try:
        import sqlite3
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO coin_requests (id, sender, recipient, amount, wallet_address, status, "
            "approval_mode, approved_by, approved_at, created_at, expires_at, transaction_hash, audit_log) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"auto-{sender}-{int(now.timestamp())}",
                sender,
                os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
                amount,
                wallet_address,
                "APPROVED",
                "automatic",
                "request_coins_handler",
                now.isoformat(),
                now.isoformat(),
                (now + timedelta(hours=24)).isoformat(),
                tx_hash,
                json.dumps({"action": "initial_coin_grant", "auto_approved": True}),
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Recorded coin request in agent DB for %s", sender)
    except Exception as e:
        logger.warning("Could not record coin request in DB: %s", e)


def _record_pending_coin_request(sender: str, amount: int, wallet_address: str) -> str:
    """Record a pending coin request in the agent SQLite database for manual approval.

    Returns the request_id so the handler can include it in the response.
    """
    db_path = os.getenv("AGENT_DB_PATH", os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/agent_coin_requests.db"))
    try:
        import sqlite3
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        request_id = f"req-{sender}-{int(now.timestamp())}"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO coin_requests (id, sender, recipient, amount, wallet_address, status, "
            "approval_mode, created_at, expires_at, audit_log) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                sender,
                os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
                amount,
                wallet_address,
                "PENDING",
                "manual",
                now.isoformat(),
                (now + timedelta(hours=24)).isoformat(),
                json.dumps({"action": "subsequent_coin_request", "auto_approved": False}),
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Recorded pending coin request %s for %s", request_id, sender)
        return request_id
    except Exception as e:
        logger.warning("Could not record pending coin request in DB: %s", e)
        return f"req-{sender}-unknown"


async def request_coins_handler(
    message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket
) -> dict[str, Any]:
    """Handle REQUEST_COINS messages.

    First request from a node: auto-transfer 100 AIT without approval.
    Subsequent requests: return pending_approval for manual review.
    """
    sender = message.get("sender_id", "unknown")
    content = message.get("content", "")
    logger.info("REQUEST_COINS received from %s: %s", sender, content)
    try:
        if "{" in content:
            json_part = content[content.index("{") :]
            data = json.loads(json_part)
            amount = data.get("amount", 0)
            wallet_address = data.get("wallet_address", "")
        else:
            amount = INITIAL_COIN_AMOUNT
            wallet_address = sender

        if not wallet_address or wallet_address == "unknown":
            return {"action": "coin_request_failed", "error": "No wallet address provided"}

        # Check if this sender has already received initial coins
        if _has_received_initial_coins(sender):
            logger.info("Coin request from %s: already received initial coins — running approval strategy", sender)
            strategy, approval_mode = _get_approval_strategy()
            approval_request = {
                "id": f"req-{sender}-{int(datetime.now(UTC).timestamp())}",
                "sender": sender,
                "recipient": os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
                "amount": amount,
                "wallet_address": wallet_address,
                "created_at": datetime.now(UTC),
            }
            approval_decision = strategy.approve(approval_request)
            if approval_decision["approved"]:
                # Strategy approved — sign and submit the transaction
                signed_tx = TransactionService().generate_signed_transaction(wallet_address, amount)
                if not signed_tx:
                    return {"action": "coin_request_failed", "error": "Failed to generate signed transaction"}
                result = _submit_transaction(signed_tx)
                if not result or not result.get("success"):
                    return {
                        "action": "coin_request_failed",
                        "error": "Blockchain rejected transaction",
                        "detail": result,
                    }
                tx_hash = result.get("transaction_hash", "")
                _record_coin_request(sender, amount, wallet_address, tx_hash)
                confirmation = {
                    "type": "COINS_TRANSFERRED",
                    "sender": os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
                    "recipient": sender,
                    "content": f"Coin request approved: {amount} AIT to {wallet_address}. Transaction: {tx_hash}",
                    "amount": amount,
                    "wallet_address": wallet_address,
                    "transaction_hash": tx_hash,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await connection_manager.send_personal_message(confirmation, sender)
                return {
                    "action": "coins_transferred",
                    "amount": amount,
                    "wallet_address": wallet_address,
                    "transaction_hash": tx_hash,
                    "status": "completed",
                    "reason": approval_decision["reason"],
                }
            else:
                # Strategy rejected or pending — record in DB for manual review
                request_id = _record_pending_coin_request(sender, amount, wallet_address)
                return {
                    "action": "coin_request_received",
                    "request_id": request_id,
                    "amount": amount,
                    "wallet_address": wallet_address,
                    "status": "pending_approval",
                    "reason": approval_decision["reason"],
                    "message": (
                        f"Coin request requires approval. Reason: {approval_decision['reason']}. "
                        "Use 'aitbc coin-requests approve <request_id>' to approve."
                    ),
                }

        # First-time request: auto-transfer initial coins
        grant_amount = INITIAL_COIN_AMOUNT
        logger.info("First-time coin request from %s — auto-transferring %s AIT to %s", sender, grant_amount, wallet_address)

        transaction = TransactionService().generate_signed_transaction(wallet_address, grant_amount)
        if not transaction:
            return {"action": "coin_request_failed", "error": "Failed to generate signed transaction"}

        result = _submit_transaction(transaction)
        if not result or not result.get("success"):
            return {"action": "coin_request_failed", "error": "Blockchain rejected transaction", "detail": result}

        tx_hash = result.get("transaction_hash", "")
        _record_coin_request(sender, grant_amount, wallet_address, tx_hash)

        # Send confirmation message back to the agent over WebSocket
        confirmation = {
            "type": "COINS_TRANSFERRED",
            "sender": os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
            "recipient": sender,
            "content": f"Transferred {grant_amount} AIT to {wallet_address}",
            "amount": grant_amount,
            "wallet_address": wallet_address,
            "transaction_hash": tx_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await connection_manager.send_personal_message(confirmation, sender)

        return {
            "action": "coins_transferred",
            "amount": grant_amount,
            "wallet_address": wallet_address,
            "transaction_hash": tx_hash,
            "status": "completed",
        }
    except Exception as e:
        logger.error("Failed to process coin request: %s", e)
        return {"action": "coin_request_failed", "error": str(e)}


def _register_builtin_handlers(connection_manager: ConnectionManager) -> None:
    """Register built-in message handlers"""
    connection_manager.register_handler("PING", ping_handler)
    connection_manager.register_handler("HELLO", hello_handler)
    connection_manager.register_handler("REQUEST_COINS", request_coins_handler)
    logger.info("Built-in handlers registered: PING, HELLO, REQUEST_COINS")
