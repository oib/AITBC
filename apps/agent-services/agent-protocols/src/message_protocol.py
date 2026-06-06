"""
Message Protocol for AITBC Agents
Handles message creation, routing, and delivery between agents
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class MessageTypes(Enum):
    """Message type enumeration"""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    DATA = "data"

class MessageProtocol:
    """Message protocol handler for agent communication"""

    def __init__(self):
        self.messages = []
        self.message_handlers = {}

    def create_message(
        self,
        sender_id: str,
        receiver_id: str,
        message_type: MessageTypes,
        content: dict[str, Any],
        message_id: str | None = None
    ) -> dict[str, Any]:
        """Create a new message"""
        if message_id is None:
            message_id = str(uuid.uuid4())

        message = {
            "message_id": message_id,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "message_type": message_type.value,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "pending"
        }

        self.messages.append(message)
        return message

    def send_message(self, message: dict[str, Any]) -> bool:
        """Send a message to the receiver"""
        try:
            message["status"] = "sent"
            message["sent_timestamp"] = datetime.now(UTC).isoformat()
            return True
        except Exception:
            message["status"] = "failed"
            return False

    def receive_message(self, message_id: str) -> dict[str, Any] | None:
        """Receive and process a message"""
        for message in self.messages:
            if message["message_id"] == message_id:
                message["status"] = "received"
                message["received_timestamp"] = datetime.now(UTC).isoformat()
                return message
        return None

    def get_messages_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """Get all messages for a specific agent"""
        return [
            msg for msg in self.messages
            if msg["sender_id"] == agent_id or msg["receiver_id"] == agent_id
        ]

class AgentMessageClient:
    """Client for agent message communication"""

    def __init__(self, agent_id: str, protocol: MessageProtocol):
        self.agent_id = agent_id
        self.protocol = protocol
        self.received_messages = []

    def send_message(
        self,
        receiver_id: str,
        message_type: MessageTypes,
        content: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a message to another agent"""
        message = self.protocol.create_message(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content=content
        )
        self.protocol.send_message(message)
        return message

    def receive_messages(self) -> list[dict[str, Any]]:
        """Receive all pending messages for this agent"""
        messages = []
        for message in self.protocol.messages:
            if (message["receiver_id"] == self.agent_id and
                message["status"] == "sent" and
                message not in self.received_messages):
                self.protocol.receive_message(message["message_id"])
                self.received_messages.append(message)
                messages.append(message)
        return messages
