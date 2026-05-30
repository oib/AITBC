"""PING message handler."""

from typing import Dict, Any
from .base_handler import BaseHandler


class PingHandler(BaseHandler):
    """Handler for PING messages - responds with PONG."""
    
    def can_handle(self, content: str) -> bool:
        """Check if content contains PING."""
        return "PING" in content.upper()
    
    async def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle PING message by sending PONG."""
        sender = message.get("sender", "unknown")
        content = message.get("content", "")
        
        self.logger.info(f"PING detected from {sender}, sending PONG")
        
        response = self.send_response(
            recipient=sender,
            content=f"PONG from {self.agent_id}"
        )
        
        if response.get("status") == "success":
            return {"status": "pong_sent", "recipient": sender}
        else:
            return {"status": "error", "error": response.get("error")}
