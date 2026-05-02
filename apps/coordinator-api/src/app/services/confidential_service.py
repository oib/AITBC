"""
Confidential Transaction Service - Wrapper for existing confidential functionality
"""

from datetime import datetime, timezone
from typing import Any

from ..models.confidential import ConfidentialTransaction
from ..services.encryption import EncryptionService
from ..services.key_management import KeyManager


class ConfidentialTransactionService:
    """Service for handling confidential transactions using existing encryption and key management"""

    def __init__(self):
        self.encryption_service = EncryptionService()
        self.key_manager = KeyManager()

    def create_confidential_transaction(
        self,
        sender: str,
        recipient: str,
        amount: int,
        viewing_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConfidentialTransaction:
        """Create a new confidential transaction"""
        # Generate viewing key if not provided
        if not viewing_key:
            viewing_key = self.key_manager.generate_viewing_key()

        # Encrypt transaction data
        encrypted_data = self.encryption_service.encrypt_transaction_data(
            {"sender": sender, "recipient": recipient, "amount": amount, "metadata": metadata or {}}
        )

        return ConfidentialTransaction(
            sender=sender,
            recipient=recipient,
            encrypted_payload=encrypted_data,
            viewing_key=viewing_key,
            created_at=datetime.now(timezone.utc),
        )

    def decrypt_transaction(self, transaction: ConfidentialTransaction, viewing_key: str) -> dict[str, Any]:
        """Decrypt a confidential transaction using viewing key"""
        return self.encryption_service.decrypt_transaction_data(transaction.encrypted_payload, viewing_key)

    def verify_transaction_access(self, transaction: ConfidentialTransaction, requester: str) -> bool:
        """Verify if requester has access to view transaction"""
        return requester in [transaction.sender, transaction.recipient]

    def get_transaction_summary(self, transaction: ConfidentialTransaction, viewer: str) -> dict[str, Any]:
        """Get transaction summary based on viewer permissions"""
        if self.verify_transaction_access(transaction, viewer):
            return self.decrypt_transaction(transaction, transaction.viewing_key)
        else:
            return {"transaction_id": transaction.id, "encrypted": True, "accessible": False}
