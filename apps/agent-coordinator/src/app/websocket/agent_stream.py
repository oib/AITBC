# mypy: ignore-errors
"""
WebSocket streaming for real-time agent messaging
Provides real-time message delivery and presence tracking
Includes automatic handler triggering for PING, REQUEST_COINS, etc.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from aitbc import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for agents"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.topic_subscriptions: dict[str, set[str]] = {}  # topic -> agent_ids
        self.agent_topics: dict[str, set[str]] = {}  # agent_id -> topics
        self.message_handlers: dict[str, list[Callable]] = {}  # message_type -> handlers
        self.agent_inboxes: dict[str, list[dict[str, Any]]] = {}  # agent_id -> queued messages

    async def connect(self, websocket: WebSocket, agent_id: str):
        """Accept a WebSocket connection from an agent"""
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        self.agent_topics[agent_id] = set()
        self.agent_inboxes[agent_id] = []
        logger.info(f"Agent {agent_id} connected via WebSocket")
        
        # Send welcome message
        await websocket.send_json({
            "type": "connection_established",
            "agent_id": agent_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "message": "WebSocket listener active - handlers will be triggered in real-time"
        })

    def disconnect(self, agent_id: str):
        """Remove agent connection"""
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]

        # Remove from topic subscriptions
        if agent_id in self.agent_topics:
            for topic in self.agent_topics[agent_id]:
                if topic in self.topic_subscriptions:
                    self.topic_subscriptions[topic].discard(agent_id)
            del self.agent_topics[agent_id]

        logger.info(f"Agent {agent_id} disconnected from WebSocket")

    async def send_personal_message(self, message: dict[str, Any], agent_id: str):
        """Send a message to a specific agent"""
        if agent_id in self.active_connections:
            try:
                websocket = self.active_connections[agent_id]
                await websocket.send_json(message)
                return True
            except Exception as e:
                logger.error(f"Error sending message to {agent_id}: {e}")
                self.disconnect(agent_id)
                return False
        return False

    async def broadcast(self, message: dict[str, Any], topic: str | None = None):
        """Broadcast message to all agents or topic subscribers"""
        if topic:
            # Send to topic subscribers
            recipients = self.topic_subscriptions.get(topic, set())
        else:
            # Send to all connected agents
            recipients = set(self.active_connections.keys())

        for agent_id in recipients:
            if agent_id in self.active_connections:
                await self.send_personal_message(message, agent_id)

        logger.info(f"Broadcast message to {len(recipients)} agents (topic: {topic})")

    async def subscribe(self, agent_id: str, topic: str):
        """Subscribe agent to topic"""
        if agent_id not in self.agent_topics:
            self.agent_topics[agent_id] = set()

        if topic not in self.topic_subscriptions:
            self.topic_subscriptions[topic] = set()

        self.agent_topics[agent_id].add(topic)
        self.topic_subscriptions[topic].add(agent_id)

        logger.info(f"Agent {agent_id} subscribed to topic {topic}")

    async def unsubscribe(self, agent_id: str, topic: str):
        """Unsubscribe agent from topic"""
        if agent_id in self.agent_topics:
            self.agent_topics[agent_id].discard(topic)

        if topic in self.topic_subscriptions:
            self.topic_subscriptions[topic].discard(agent_id)

        logger.info(f"Agent {agent_id} unsubscribed from topic {topic}")

    def get_connected_agents(self) -> list[str]:
        """Get list of connected agent IDs"""
        return list(self.active_connections.keys())

    def get_topic_subscribers(self, topic: str) -> set[str]:
        """Get subscribers for a topic"""
        return self.topic_subscriptions.get(topic, set())

    def register_handler(self, message_type: str, handler: Callable):
        """Register a message handler for specific message type"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
        logger.info(f"Registered handler for message type: {message_type}")

    async def trigger_handlers(self, message: dict[str, Any], websocket: WebSocket) -> dict[str, Any]:
        """Trigger all registered handlers for the message type"""
        content = message.get("content", "")
        sender_id = message.get("sender_id", "unknown")
        
        # Determine message type based on content
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
                results.append({
                    "handler": handler.__name__,
                    "result": result,
                    "success": True
                })
            except Exception as e:
                logger.error(f"Handler error: {e}")
                results.append({
                    "handler": handler.__name__,
                    "error": str(e),
                    "success": False
                })
        
        return {
            "message_type": message_type,
            "handlers_triggered": len(handlers),
            "results": results
        }

    async def deliver_queued_messages(self, agent_id: str):
        """Deliver queued messages when agent connects"""
        if agent_id in self.agent_inboxes and self.agent_inboxes[agent_id]:
            queued_messages = self.agent_inboxes[agent_id].copy()
            self.agent_inboxes[agent_id].clear()
            
            for message in queued_messages:
                await self.send_personal_message(message, agent_id)
            
            logger.info(f"Delivered {len(queued_messages)} queued messages to {agent_id}")


class AgentStreamHandler:
    """WebSocket handler for agent message streaming"""

    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager

    async def handle_message_stream(self, websocket: WebSocket, agent_id: str):
        """Handle WebSocket message stream for an agent"""
        await self.connection_manager.connect(websocket, agent_id)
        
        # Deliver any queued messages
        await self.connection_manager.deliver_queued_messages(agent_id)

        try:
            while True:
                # Receive message from agent
                data = await websocket.receive_json()

                # Process message
                message_type = data.get("type", "message")
                payload = data.get("payload", {})

                if message_type == "subscribe":
                    # Subscribe to topic
                    topic = payload.get("topic")
                    if topic:
                        await self.connection_manager.subscribe(agent_id, topic)
                        await websocket.send_json({
                            "type": "subscription_confirmed",
                            "topic": topic,
                            "timestamp": datetime.now(UTC).isoformat()
                        })

                elif message_type == "unsubscribe":
                    # Unsubscribe from topic
                    topic = payload.get("topic")
                    if topic:
                        await self.connection_manager.unsubscribe(agent_id, topic)
                        await websocket.send_json({
                            "type": "unsubscription_confirmed",
                            "topic": topic,
                            "timestamp": datetime.now(UTC).isoformat()
                        })

                elif message_type == "message":
                    # Trigger handlers for message content
                    message_data = {
                        "sender_id": agent_id,
                        "content": payload.get("content", ""),
                        "recipient_id": payload.get("recipient_id"),
                        "timestamp": datetime.now(UTC).isoformat()
                    }
                    
                    # Trigger handlers
                    handler_results = await self.connection_manager.trigger_handlers(message_data, websocket)
                    
                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "handler_acknowledgment",
                        "message_id": data.get("id"),
                        "handler_results": handler_results,
                        "timestamp": datetime.now(UTC).isoformat()
                    })
                    
                    # Forward message to recipient if specified
                    recipient_id = payload.get("recipient_id")
                    if recipient_id:
                        forward_data = {
                            "type": "message",
                            "sender_id": agent_id,
                            "recipient_id": recipient_id,
                            "content": payload.get("content"),
                            "timestamp": datetime.now(UTC).isoformat()
                        }
                        await self.connection_manager.send_personal_message(forward_data, recipient_id)

                elif message_type == "broadcast":
                    # Broadcast message to topic
                    topic = payload.get("topic")
                    broadcast_data = {
                        "type": "broadcast",
                        "sender_id": agent_id,
                        "content": payload.get("content"),
                        "topic": topic,
                        "timestamp": datetime.now(UTC).isoformat()
                    }
                    await self.connection_manager.broadcast(broadcast_data, topic)

                elif message_type == "heartbeat":
                    # Respond to heartbeat
                    await websocket.send_json({
                        "type": "heartbeat_ack",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

                else:
                    logger.warning(f"Unknown message type: {message_type}")

        except WebSocketDisconnect:
            self.connection_manager.disconnect(agent_id)
        except Exception as e:
            logger.error(f"Error in message stream for {agent_id}: {e}")
            self.connection_manager.disconnect(agent_id)

    async def handle_presence_stream(self, websocket: WebSocket, agent_id: str):
        """Handle WebSocket presence stream for an agent"""
        await self.connection_manager.connect(websocket, agent_id)

        try:
            # Send initial presence update
            await websocket.send_json({
                "type": "presence_update",
                "agent_id": agent_id,
                "status": "online",
                "connected_agents": self.connection_manager.get_connected_agents(),
                "timestamp": datetime.now(UTC).isoformat()
            })

            while True:
                # Wait for presence updates
                data = await websocket.receive_json()

                message_type = data.get("type", "presence")

                if message_type == "presence":
                    # Broadcast presence update
                    presence_data = {
                        "type": "presence_update",
                        "agent_id": agent_id,
                        "status": data.get("status", "online"),
                        "timestamp": datetime.now(UTC).isoformat()
                    }
                    await self.connection_manager.broadcast(presence_data)

                elif message_type == "get_agents":
                    # Send list of connected agents
                    await websocket.send_json({
                        "type": "agents_list",
                        "agents": self.connection_manager.get_connected_agents(),
                        "timestamp": datetime.now(UTC).isoformat()
                    })

                elif message_type == "heartbeat":
                    # Respond to heartbeat
                    await websocket.send_json({
                        "type": "heartbeat_ack",
                        "timestamp": datetime.now(UTC).isoformat()
                    })

        except WebSocketDisconnect:
            self.connection_manager.disconnect(agent_id)
            # Broadcast agent offline
            offline_data = {
                "type": "presence_update",
                "agent_id": agent_id,
                "status": "offline",
                "timestamp": datetime.now(UTC).isoformat()
            }
            await self.connection_manager.broadcast(offline_data)
        except Exception as e:
            logger.error(f"Error in presence stream for {agent_id}: {e}")
            self.connection_manager.disconnect(agent_id)


# Global connection manager
_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get global connection manager"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
        # Register built-in handlers
        _register_builtin_handlers(_connection_manager)
    return _connection_manager


# Built-in handlers
async def ping_handler(message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket) -> dict[str, Any]:
    """Handle PING messages with automatic PONG response"""
    sender = message.get("sender_id", "unknown")
    recipient = message.get("recipient_id", "unknown")
    
    logger.info(f"PING received from {sender}, triggering PONG")
    
    # Send PONG response
    pong_message = {
        "type": "PONG",
        "sender": recipient,
        "recipient": sender,
        "content": f"PONG from {recipient}",
        "timestamp": datetime.now(UTC).isoformat(),
        "original_message_id": message.get("id")
    }
    
    await connection_manager.send_personal_message(pong_message, sender)
    
    return {
        "action": "pong_sent",
        "recipient": sender,
        "original_ping": message.get("id")
    }


async def hello_handler(message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket) -> dict[str, Any]:
    """Handle HELLO messages"""
    sender = message.get("sender_id", "unknown")
    logger.info(f"HELLO received from {sender}")
    
    return {
        "action": "hello_acknowledged",
        "sender": sender
    }


async def request_coins_handler(message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket) -> dict[str, Any]:
    """Handle REQUEST_COINS messages"""
    sender = message.get("sender_id", "unknown")
    content = message.get("content", "")
    
    logger.info(f"REQUEST_COINS received from {sender}: {content}")
    
    # Parse amount from content
    try:
        if "{" in content:
            data = json.loads(content)
            amount = data.get("amount", 0)
            wallet_address = data.get("wallet_address", "")
        else:
            amount = 100  # Default
            wallet_address = sender
        
        logger.info(f"Coin request: {amount} AIT to {wallet_address}")
        
        return {
            "action": "coin_request_received",
            "amount": amount,
            "wallet_address": wallet_address,
            "status": "pending_approval"
        }
    except Exception as e:
        logger.error(f"Failed to parse coin request: {e}")
        return {
            "action": "coin_request_failed",
            "error": str(e)
        }


def _register_builtin_handlers(connection_manager: ConnectionManager):
    """Register built-in message handlers"""
    connection_manager.register_handler("PING", ping_handler)
    connection_manager.register_handler("HELLO", hello_handler)
    connection_manager.register_handler("REQUEST_COINS", request_coins_handler)
    logger.info("Built-in handlers registered: PING, HELLO, REQUEST_COINS")
