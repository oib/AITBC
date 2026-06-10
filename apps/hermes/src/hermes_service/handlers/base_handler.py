"""Base handler class for Hermes message handlers."""

import logging
from abc import ABC, abstractmethod
from typing import Any


class BaseHandler(ABC):
    """Abstract base class for message handlers."""

    def __init__(self, coordinator_url: str, agent_id: str):
        self.coordinator_url = coordinator_url
        self.agent_id = agent_id
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def can_handle(self, content: str) -> bool:
        """Check if this handler can process the given message content."""
        pass

    @abstractmethod
    async def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        """Process the message and return a response."""
        pass

    def send_response(self, recipient: str, content: str, message_type: str = "direct") -> dict[str, Any]:
        """Send a response message via the Coordinator API."""
        import requests

        try:
            response = requests.post(
                f"{self.coordinator_url}/api/v1/agent/messages/send",
                json={
                    "sender": self.agent_id,
                    "recipient": recipient,
                    "content": {"text": content},
                    "message_type": message_type,
                    "encrypt": False
                },
                timeout=10
            )
            if response.status_code == 200:
                self.logger.info(f"Response sent successfully to {recipient}")
                return {"status": "success", "response": response.json()}
            else:
                self.logger.error(f"Failed to send response: {response.text}")
                return {"status": "error", "error": response.text}
        except Exception as e:
            self.logger.error(f"Error sending response: {e}")
            return {"status": "error", "error": str(e)}
