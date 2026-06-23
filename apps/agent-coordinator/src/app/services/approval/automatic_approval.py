"""Automatic approval strategy - approves based on amount and island membership.

Moved from hermes_service.handlers.strategies.automatic_approval in v0.5.9 §3.
"""

import os
from typing import Any

from ..island_members import get_island_members
from .base_approval import ApprovalStrategy


class AutomaticApprovalStrategy(ApprovalStrategy):
    """Automatic approval strategy based on rules."""

    def __init__(self, coordinator_url: str, agent_id: str):
        super().__init__(coordinator_url, agent_id)
        self.max_auto_amount = int(os.getenv("COIN_AUTOMATIC_APPROVAL_AMOUNT", "1000"))

    def approve(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Approve automatically if amount is under threshold and sender is island member.

        Returns:
            Dictionary with approval decision.
        """
        amount = request.get("amount", 0)
        sender = request.get("sender", "")

        # Check amount threshold
        if amount > self.max_auto_amount:
            reason = f"Amount {amount} exceeds auto-approval threshold {self.max_auto_amount}"
            self.log_decision(request, approved=False, reason=reason)
            return {"approved": False, "reason": reason, "signed_transaction": None}

        # Check if sender is island member
        island_members = get_island_members()
        if sender not in island_members:
            reason = f"Sender {sender} is not a trusted island member"
            self.log_decision(request, approved=False, reason=reason)
            return {"approved": False, "reason": reason, "signed_transaction": None}

        # Auto-approve
        reason = f"Auto-approved: amount {amount} <= {self.max_auto_amount} and sender is island member"
        self.log_decision(request, approved=True, reason=reason)

        return {
            "approved": True,
            "reason": reason,
            "signed_transaction": None,  # Will be generated later
        }
