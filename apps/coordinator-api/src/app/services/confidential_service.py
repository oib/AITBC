"""
Confidential Transaction Service - Wrapper for existing confidential functionality
"""

from datetime import UTC, datetime
from typing import Any

from ..contexts.security.services.encryption import EncryptionService
from ..contexts.security.services.key_management import KeyManager, MockHSMStorage
from ..models.confidential import ConfidentialTransactionDB as ConfidentialTransaction


class ConfidentialTransactionService:
    """Service for handling confidential transactions using existing encryption and key management"""

    def __init__(self) -> None:
        self.key_manager = KeyManager(storage_backend=MockHSMStorage())
        self.encryption_service = EncryptionService(key_manager=self.key_manager)  # type: ignore[arg-type]

    def create_confidential_transaction(
        self,
        sender: str,
        recipient: str,
        amount: int,
        viewing_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConfidentialTransaction:
        """Create a new confidential transaction"""
        import secrets

        if not viewing_key:
            viewing_key = secrets.token_hex(32)

        encrypted = self.encryption_service.encrypt(
            {"sender": sender, "recipient": recipient, "amount": amount, "metadata": metadata or {}},
            participants=[sender, recipient],
        )

        return ConfidentialTransaction(
            participants=[sender, recipient],
            encrypted_data=str(encrypted.to_dict()).encode(),
            status="created",
            confidential=True,
            created_at=datetime.now(UTC),
        )

    def decrypt_transaction(self, transaction: ConfidentialTransaction, viewing_key: str) -> dict[str, Any]:
        """Decrypt a confidential transaction using viewing key"""
        from ..contexts.security.services.encryption import EncryptedData

        raw = transaction.encrypted_data
        if not raw:
            return {}
        import ast

        encrypted = EncryptedData.from_dict(ast.literal_eval(raw.decode()))
        participants: list[str] = list(transaction.participants) if transaction.participants else []
        requester = participants[0] if participants else ""
        result: dict[str, Any] = self.encryption_service.decrypt(encrypted, requester)
        return result

    def verify_transaction_access(self, transaction: ConfidentialTransaction, requester: str) -> bool:
        """Verify if requester has access to view transaction"""
        return requester in (transaction.participants or [])

    def get_transaction_summary(self, transaction: ConfidentialTransaction, viewer: str) -> dict[str, Any]:
        """Get transaction summary based on viewer permissions"""
        if self.verify_transaction_access(transaction, viewer):
            return self.decrypt_transaction(transaction, viewer)
        else:
            return {"transaction_id": str(transaction.id), "encrypted": True, "accessible": False}
