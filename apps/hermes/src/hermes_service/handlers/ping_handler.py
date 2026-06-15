"""PING message handler."""

from typing import Any

from .base_handler import BaseHandler


class PingHandler(BaseHandler):
    """Handler for PING messages - responds with PONG."""

    def can_handle(self, content: str) -> bool:
        """Check if content contains PING."""
        return "PING" in content.upper()

    async def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle PING message by sending PONG."""
        sender = message.get("sender", "unknown")
        message.get("content", "")
        self.logger.info("PING detected from %s, sending PONG", sender)
        response = self.send_response(recipient=sender, content=f"PONG from {self.agent_id}")
        if response.get("status") == "success":
            return {"status": "pong_sent", "recipient": sender}
        else:
            return {"status": "error", "error": response.get("error")}
