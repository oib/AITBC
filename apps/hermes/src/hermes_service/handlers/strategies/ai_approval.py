"""AI approval strategy - uses Ollama to evaluate requests."""

import os
from datetime import datetime, timedelta
from typing import Any

import requests

from ...storage import CoinRequest, get_db_session  # type: ignore
from .base_approval import ApprovalStrategy


class AIApprovalStrategy(ApprovalStrategy):
    """AI approval strategy using Ollama nemotron-3-super:cloud model."""

    def __init__(self, coordinator_url: str, agent_id: str):
        super().__init__(coordinator_url, agent_id)
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "nemotron-3-super:cloud")
        self.enabled = os.getenv("ENABLE_AI_APPROVAL", "false").lower() == "true"

    def get_request_history(self, sender: str, days: int = 1) -> list[Any]:
        """Get request history for sender from last N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        with get_db_session() as session:
            requests = session.query(CoinRequest).filter(CoinRequest.sender == sender, CoinRequest.created_at >= cutoff).all()

            return [{"amount": r.amount, "status": r.status.value, "created_at": r.created_at.isoformat()} for r in requests]

    def approve(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Use AI to evaluate and approve/reject request.

        Returns:
            Dictionary with AI approval decision.
        """
        if not self.enabled:
            reason = "AI approval is disabled"
            self.log_decision(request, approved=False, reason=reason)
            return {"approved": False, "reason": reason, "signed_transaction": None}

        sender = request.get("sender", "")
        amount = request.get("amount", 0)
        wallet_address = request.get("wallet_address", "")

        # Get request history
        history = self.get_request_history(sender, days=1)

        # Build prompt for AI
        prompt = self._build_prompt(sender, amount, wallet_address, history)

        try:
            # Query Ollama
            response = requests.post(
                f"{self.ollama_url}/api/generate", json={"model": self.model, "prompt": prompt, "stream": False}, timeout=30
            )

            if response.status_code != 200:
                reason = f"Ollama API error: {response.status_code}"
                self.log_decision(request, approved=False, reason=reason)
                return {"approved": False, "reason": reason, "signed_transaction": None}

            result = response.json()
            ai_response = result.get("response", "").strip().lower()

            # Parse AI decision
            approved = "approve" in ai_response or "yes" in ai_response
            reason = f"AI decision: {result.get('response', 'No reason provided')}"

            self.log_decision(request, approved=approved, reason=reason)

            return {"approved": approved, "reason": reason, "signed_transaction": None}

        except Exception as e:
            reason = f"AI approval error: {str(e)}"
            self.log_decision(request, approved=False, reason=reason)
            return {"approved": False, "reason": reason, "signed_transaction": None}

    def _build_prompt(self, sender: str, amount: int, wallet_address: str, history: list[Any]) -> str:
        """Build prompt for AI evaluation."""
        history_text = (
            "\n".join([f"- {h['amount']} AIT, status: {h['status']}, at {h['created_at']}" for h in history])
            if history
            else "No recent requests"
        )

        prompt = f"""You are an AI assistant for approving coin transfer requests in a blockchain network.

Current request:
- Sender: {sender}
- Amount: {amount} AIT
- Wallet address: {wallet_address}

Request history (last 1 day):
{history_text}

Evaluate this request and respond with either "APPROVE" or "REJECT" followed by a brief reason.
Consider factors like:
- Request amount
- Sender's request history
- Pattern of requests

Response format: "APPROVE: [reason]" or "REJECT: [reason]" """

        return prompt
