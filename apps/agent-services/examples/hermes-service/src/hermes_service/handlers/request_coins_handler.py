"""REQUEST_COINS message handler."""

from typing import Dict, Any
from .base_handler import BaseHandler


class RequestCoinsHandler(BaseHandler):
    """Handler for REQUEST_COINS messages - acknowledges coin requests."""
    
    def can_handle(self, content: str) -> bool:
        """Check if content contains REQUEST_COINS."""
        return "REQUEST_COINS" in content.upper() or "request coins" in content.lower()
    
    async def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle REQUEST_COINS message by sending acknowledgment."""
        sender = message.get("sender", "unknown")
        content = message.get("content", "")
        
        self.logger.info(f"REQUEST_COINS detected from {sender}")
        
        response = self.send_response(
            recipient=sender,
            content=f"Coin request received from {sender}. Request pending approval."
        )
        
        if response.get("status") == "success":
            return {"status": "coin_request_received", "recipient": sender}
        else:
            return {"status": "error", "error": response.get("error")}
