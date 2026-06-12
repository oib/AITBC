# mypy: ignore-errors
"""Transaction service for generating signed coin transfer transactions."""

import json
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519


class TransactionService:
    """Service for generating signed blockchain transactions."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Get blockchain RPC URL
        self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        # Get chain ID
        self.chain_id = os.getenv("CHAIN_ID", "ait-mainnet")
        # Get genesis wallet private key (for signing)
        self.genesis_private_key = os.getenv("GENESIS_PRIVATE_KEY")
        # Get genesis wallet address
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
            from aitbc import AITBCHTTPClient
            http_client = AITBCHTTPClient(base_url=self.rpc_url, timeout=5)
            account_data = http_client.get(f"/rpc/account/{address}")
            return account_data.get("nonce", 0)
        except Exception as e:
            self.logger.error(f"Error getting nonce: {e}")

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
            from aitbc import AITBCHTTPClient
            http_client = AITBCHTTPClient(base_url=self.rpc_url, timeout=5)
            account_data = http_client.get(f"/rpc/account/{address}")
            return account_data.get("balance", 0)
        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")

        return 0

    def generate_signed_transaction(
        self,
        to_address: str,
        amount: int,
        fee: int = 1000
    ) -> dict[str, Any] | None:
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
            # Get actual nonce from blockchain
            actual_nonce = self.get_nonce(self.genesis_address)

            # Load private key
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(self.genesis_private_key)
            )

            # Create transaction in format expected by blockchain RPC
            transaction = {
                "from": self.genesis_address,
                "to": to_address,
                "amount": amount,
                "nonce": actual_nonce,
                "fee": fee,
                "type": "TRANSFER"
            }

            # Sign transaction
            message = json.dumps(transaction, sort_keys=True).encode()
            signature = private_key.sign(message)
            transaction["signature"] = signature.hex()

            self.logger.info(f"Generated signed transaction for {amount} to {to_address}")

            return transaction

        except Exception as e:
            self.logger.error(f"Error generating signed transaction: {e}")
            return None
