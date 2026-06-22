"""Transaction service for generating signed coin transfer transactions."""

import json
import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519

from aitbc.aitbc_logging import get_logger


class TransactionService:
    """Service for generating signed blockchain transactions."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        self.chain_id = os.getenv("CHAIN_ID", "")
        self.genesis_private_key = os.getenv("GENESIS_PRIVATE_KEY")
        self.genesis_address = os.getenv("GENESIS_ADDRESS")

    def get_nonce(self, address: str) -> int:
        """
        Get current nonce for an address from blockchain.

        Args:
            address: Wallet address

        Returns:
            Current nonce
        """
        try:
            from aitbc.network import AITBCHTTPClient

            http_client = AITBCHTTPClient(base_url=self.rpc_url, timeout=5)
            account_data = http_client.get(f"/rpc/account/{address}")
            return int(account_data.get("nonce", 0))
        except Exception as e:
            self.logger.error("Error getting nonce: %s", e)
        return 0

    def get_balance(self, address: str) -> int:
        """
        Get current balance for an address from blockchain.

        Args:
            address: Wallet address

        Returns:
            Current balance
        """
        try:
            from aitbc.network import AITBCHTTPClient

            http_client = AITBCHTTPClient(base_url=self.rpc_url, timeout=5)
            account_data = http_client.get(f"/rpc/account/{address}")
            return int(account_data.get("balance", 0))
        except Exception as e:
            self.logger.error("Error getting balance: %s", e)
        return 0

    def generate_signed_transaction(self, to_address: str, amount: int, fee: int = 10) -> dict[str, Any] | None:
        """
        Generate a signed blockchain transaction.

        Args:
            to_address: Recipient wallet address
            amount: Amount to transfer (in smallest unit)
            fee: Transaction fee

        Returns:
            Dictionary with signed transaction or None if error
        """
        if not self.genesis_private_key:
            self.logger.error("GENESIS_PRIVATE_KEY not set - cannot sign transactions")
            return None
        if not self.genesis_address:
            self.logger.error("GENESIS_ADDRESS not set - cannot create transactions")
            return None
        try:
            actual_nonce = self.get_nonce(self.genesis_address)
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.genesis_private_key))
            transaction = {
                "from": self.genesis_address,
                "to": to_address,
                "amount": amount,
                "nonce": actual_nonce,
                "fee": fee,
                "type": "TRANSFER",
            }
            message = json.dumps(transaction, sort_keys=True).encode()
            signature = private_key.sign(message)
            transaction["signature"] = signature.hex()
            self.logger.info("Generated signed transaction for %s to %s", amount, to_address)
            return transaction
        except Exception as e:
            self.logger.error("Error generating signed transaction: %s", e)
            return None
