"""Base approval strategy class."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging


class ApprovalStrategy(ABC):
    """Abstract base class for approval strategies."""
    
    def __init__(self, coordinator_url: str, agent_id: str):
        self.coordinator_url = coordinator_url
        self.agent_id = agent_id
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def approve(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Approve or reject a coin request.
        
        Args:
            request: Dictionary containing request details (sender, amount, wallet_address, etc.)
        
        Returns:
            Dictionary with approval decision:
            {
                "approved": bool,
                "reason": str,
                "signed_transaction": Optional[str]
            }
        """
        pass
    
    def log_decision(self, request: Dict[str, Any], approved: bool, reason: str):
        """Log approval decision for audit trail."""
        decision = "APPROVED" if approved else "REJECTED"
        self.logger.info(
            f"Approval decision: {decision} | "
            f"Mode: {self.__class__.__name__} | "
            f"Sender: {request.get('sender')} | "
            f"Amount: {request.get('amount')} | "
            f"Reason: {reason}"
        )
