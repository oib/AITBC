"""Approval strategy modules.

Moved from hermes_service.handlers.strategies in v0.5.9 §3.
"""

from .ai_approval import AIApprovalStrategy
from .automatic_approval import AutomaticApprovalStrategy
from .base_approval import ApprovalStrategy
from .manual_approval import ManualApprovalStrategy

__all__ = ["ApprovalStrategy", "ManualApprovalStrategy", "AutomaticApprovalStrategy", "AIApprovalStrategy"]
