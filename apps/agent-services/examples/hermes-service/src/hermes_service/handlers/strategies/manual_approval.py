"""Manual approval strategy - stores requests as pending for CLI approval."""

from typing import Any

from .base_approval import ApprovalStrategy


class ManualApprovalStrategy(ApprovalStrategy):
    """Manual approval strategy - requires CLI approval."""

    def approve(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Store request as pending for manual CLI approval.
        
        Returns:
            Dictionary indicating request is pending manual approval.
        """
        self.log_decision(request, approved=False, reason="Pending manual approval via CLI")

        return {
            "approved": False,
            "reason": "Pending manual approval via CLI",
            "signed_transaction": None
        }
