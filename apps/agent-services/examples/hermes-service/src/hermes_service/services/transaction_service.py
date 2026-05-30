"""Transaction service for generating signed coin transfer transactions."""

import os
import json
import ed25519
from typing import Dict, Any, Optional
import logging


class TransactionService:
    """Service for generating signed blockchain transactions."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Get blockchain RPC URL
        self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")
        # Get chain ID
        self.chain_id = os.getenv("CHAIN_ID", "ait-mainnet")
        # Get genesis wallet private key (for signing)
        self.genesis_private_key = os.getenv("GENESIS_PRIVATE_KEY")
        # Get genesis wallet address
        self.genesis_address = os.getenv("GENESIS_ADDRESS")
    
    def generate_signed_transaction(
        self,
        to_address: str,
        amount: int,
        fee: int = 1000
    ) -> Optional[Dict[str, Any]]:
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
            # Load private key
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(self.genesis_private_key)
            )
            
            # Create transaction payload
            transaction = {
                "type": "TRANSFER",
                "chain_id": self.chain_id,
                "from": self.genesis_address,
                "nonce": 0,  # Will need to get actual nonce from blockchain
                "fee": fee,
                "payload": {
                    "recipient": to_address,
                    "amount": amount
                }
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
    
    def get_nonce(self, address: str) -> int:
        """
        Get current nonce for an address from blockchain.
        
        Args:
            address: Wallet address
        
        Returns:
            Current nonce
        """
        try:
            import requests
            response = requests.get(
                f"{self.rpc_url}/rpc/accounts/{address}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("nonce", 0)
        except Exception as e:
            self.logger.error(f"Error getting nonce: {e}")
        
        return 0
