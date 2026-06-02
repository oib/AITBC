"""REQUEST_COINS message handler with approval workflow."""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Any

from ..services import TransactionService
from ..storage import CoinRequest, CoinRequestStatus, get_db_session, init_db
from .base_handler import BaseHandler
from .strategies import AIApprovalStrategy, AutomaticApprovalStrategy, ManualApprovalStrategy


class RequestCoinsHandler(BaseHandler):
    """Handler for REQUEST_COINS messages with approval workflow."""

    def __init__(self, coordinator_url: str, agent_id: str):
        super().__init__(coordinator_url, agent_id)
        # Initialize database
        init_db()

        # Initialize transaction service
        self.transaction_service = TransactionService()

        # Get approval mode
        self.approval_mode = os.getenv("COIN_APPROVAL_MODE", "manual").lower()

        # Initialize appropriate strategy
        if self.approval_mode == "automatic":
            self.strategy = AutomaticApprovalStrategy(coordinator_url, agent_id)
        elif self.approval_mode == "ai":
            self.strategy = AIApprovalStrategy(coordinator_url, agent_id)
        else:
            self.strategy = ManualApprovalStrategy(coordinator_url, agent_id)

        self.logger.info(f"RequestCoinsHandler initialized with mode: {self.approval_mode}")

    def can_handle(self, content: str) -> bool:
        """Check if content contains REQUEST_COINS."""
        return "REQUEST_COINS" in content.upper() or "request coins" in content.lower()

    def parse_request(self, content: str) -> dict[str, Any]:
        """Parse REQUEST_COINS message to extract amount and wallet address."""
        # Try JSON format first
        import json
        try:
            data = json.loads(content)
            if "cmd" in data and data.get("cmd") == "REQUEST_COINS":
                return {
                    "amount": int(data.get("amount", 0)),
                    "wallet_address": data.get("to_address", "")
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Try format: REQUEST_COINS:1000 to <address>
        colon_match = re.search(r'REQUEST_COINS:\s*(\d+)', content, re.IGNORECASE)
        if colon_match:
            amount = int(colon_match.group(1))
            # Try to extract wallet address (e.g., "to address 0x..." or "to 0x...")
            address_match = re.search(r'(?:to\s+address|to)\s+([a-zA-Z0-9]+)', content, re.IGNORECASE)
            wallet_address = address_match.group(1) if address_match else ""
            return {
                "amount": amount,
                "wallet_address": wallet_address
            }

        # Fallback to regex parsing (natural language)
        # Try to extract amount (e.g., "2000 ait coins")
        amount_match = re.search(r'(\d+)\s*(?:ait\s+)?coins?', content, re.IGNORECASE)
        amount = int(amount_match.group(1)) if amount_match else 0

        # Try to extract wallet address (e.g., "to address 0x..." or "to 0x...")
        address_match = re.search(r'(?:to\s+address|to)\s+([a-zA-Z0-9]+)', content, re.IGNORECASE)
        wallet_address = address_match.group(1) if address_match else ""

        return {
            "amount": amount,
            "wallet_address": wallet_address
        }

    async def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle REQUEST_COINS message with approval workflow."""
        sender = message.get("sender", "unknown")
        content = message.get("content", "")
        msg_id = message.get("id", "")

        self.logger.info(f"REQUEST_COINS detected from {sender}")

        # Parse request details
        request_details = self.parse_request(content)
        amount = request_details["amount"]
        wallet_address = request_details["wallet_address"]

        self.logger.info(f"Parsed request: amount={amount}, wallet_address={wallet_address}")

        if amount == 0:
            self.logger.error("Could not parse amount from request")
            return {"status": "error", "error": "Could not parse amount from request"}

        if not wallet_address:
            self.logger.error("Could not parse wallet address from request")
            return {"status": "error", "error": "Could not parse wallet address from request"}

        # Create request ID
        request_id = f"req-{msg_id}" if msg_id else f"req-{datetime.utcnow().timestamp()}"

        # Prepare request for approval
        approval_request = {
            "id": request_id,
            "sender": sender,
            "recipient": self.agent_id,
            "amount": amount,
            "wallet_address": wallet_address,
            "created_at": datetime.utcnow()
        }

        # Get approval decision
        approval_decision = self.strategy.approve(approval_request)

        # Generate signed transaction if approved
        signed_transaction = None
        if approval_decision["approved"]:
            signed_tx = self.transaction_service.generate_signed_transaction(
                to_address=wallet_address,
                amount=amount
            )
            if signed_tx:
                signed_transaction = json.dumps(signed_tx)
                approval_decision["signed_transaction"] = signed_transaction

        # Store in database
        with get_db_session() as session:
            coin_request = CoinRequest(
                id=request_id,
                sender=sender,
                recipient=self.agent_id,
                amount=amount,
                wallet_address=wallet_address,
                status=CoinRequestStatus.APPROVED if approval_decision["approved"] else CoinRequestStatus.PENDING,
                approval_mode=self.approval_mode,
                approved_by=self.strategy.__class__.__name__,
                approved_at=datetime.utcnow() if approval_decision["approved"] else None,
                rejection_reason=approval_decision["reason"] if not approval_decision["approved"] else None,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=30),
                signed_transaction=signed_transaction,
                audit_log=f"Mode: {self.approval_mode}, Decision: {approval_decision['approved']}, Reason: {approval_decision['reason']}"
            )
            session.add(coin_request)
            session.commit()
            self.logger.info(f"Stored coin request in database: {request_id}")

        # Send response based on approval
        if approval_decision["approved"]:
            response_content = f"Coin request approved: {amount} AIT to {wallet_address}. Transaction pending execution."
        else:
            response_content = f"Coin request received: {amount} AIT to {wallet_address}. Status: {approval_decision['reason']}"

        response = self.send_response(
            recipient=sender,
            content=response_content
        )

        if response.get("status") == "success":
            return {
                "status": "coin_request_processed",
                "request_id": request_id,
                "approved": approval_decision["approved"],
                "reason": approval_decision["reason"]
            }
        else:
            return {"status": "error", "error": response.get("error")}
