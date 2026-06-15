"""Base approval strategy class."""
import logging
from abc import ABC, abstractmethod
from typing import Any


class ApprovalStrategy(ABC):
    """Abstract base class for approval strategies."""

    def __init__(self, coordinator_url: str, agent_id: str):
        self.coordinator_url = coordinator_url
        self.agent_id = agent_id
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def approve(self, request: dict[str, Any]) -> dict[str, Any]:
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

    def log_decision(self, request: dict[str, Any], approved: bool, reason: str) -> None:
        """Log approval decision for audit trail."""
        decision = 'APPROVED' if approved else 'REJECTED'
        self.logger.info('Approval decision: %s | Mode: %s | Sender: %s | Amount: %s | Reason: %s', decision, self.__class__.__name__, request.get('sender'), request.get('amount'), reason)
