"""Transaction service for generating signed coin transfer transactions.

Moved from hermes_service.services.transaction_service in v0.5.9 §1
to provide a shared implementation for both the Agent Coordinator and CLI.

Signatures are secp256k1 (Ethereum-style) and MUST stay byte-for-byte
compatible with the blockchain node's verifier
(``apps/blockchain-node/src/aitbc_chain/rpc/utils.py:verify_transaction_signature``):
the signed message is the keccak256 hash of the canonical JSON
(``sort_keys=True, separators=(",", ":")``) of the transaction fields
``{from, to, amount, fee, nonce, payload, type}`` — i.e. excluding the
``signature`` and ``chain_id`` fields (v0.5.16 §A1).
"""

import json
import os
from typing import Any

from aitbc.aitbc_logging import get_logger

# Transaction fields covered by the signature, in the exact shape the node
# verifier reconstructs. Keep in sync with the node verifier (see module docstring).
_SIGNED_FIELDS = ("from", "to", "amount", "fee", "nonce", "payload", "type", "chain_id")


def _canonical_signing_message(tx: dict[str, Any]) -> bytes:
    """Return the exact bytes that are hashed and signed for a transaction.

    Must remain identical to the node verifier's reconstruction:
    ``json.dumps(<signed fields>, sort_keys=True, separators=(",", ":"))``.
    """
    signed = {k: tx[k] for k in _SIGNED_FIELDS if k in tx}
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()


class TransactionService:
    """Service for generating signed blockchain transactions."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        self.chain_id = os.getenv("CHAIN_ID", "ait-hub")
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

    def generate_signed_transaction(
        self, to_address: str, amount: int, fee: int = 36, chain_id: str | None = None
    ) -> dict[str, Any] | None:
        """
        Generate a signed blockchain transaction.

        Args:
            to_address: Recipient wallet address
            amount: Amount to transfer (in smallest unit)
            fee: Transaction fee
            chain_id: Chain identifier (defaults to self.chain_id from env)

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
            from eth_keys import keys
            from eth_utils import keccak

            private_key = keys.PrivateKey(bytes.fromhex(self.genesis_private_key.removeprefix("0x")))
            signer_address = private_key.public_key.to_checksum_address()
            if self.genesis_address.lower() != signer_address.lower():
                # The node recovers the signer from the signature and compares it to
                # `from`; a mismatch here guarantees a 403 rejection downstream, so we
                # fail closed rather than emit an unverifiable transaction.
                self.logger.error(
                    "GENESIS_ADDRESS (%s) does not match the secp256k1 address derived from "
                    "GENESIS_PRIVATE_KEY (%s); transactions would be rejected by the blockchain "
                    "node. Check the genesis key configuration.",
                    self.genesis_address,
                    signer_address,
                )
                return None

            actual_chain_id = chain_id if chain_id is not None else self.chain_id
            actual_nonce = self.get_nonce(signer_address)

            # Replicate the node's payload defaulting: for a TRANSFER posted via the
            # `from`/`to` aliases, the server injects `amount` (only) into the payload.
            transaction: dict[str, Any] = {
                "from": signer_address,
                "to": to_address,
                "amount": amount,
                "fee": fee,
                "nonce": actual_nonce,
                "payload": {"amount": amount},
                "type": "TRANSFER",
            }

            # chain_id is part of both the POST body (for routing) and the signed
            # message (to prevent cross-chain replay). It must be set before signing.
            transaction["chain_id"] = actual_chain_id

            # Sign with secp256k1 over the canonical message (matches the node verifier).
            # eth_keys produces a 65-byte r||s||v signature with v in {0, 1}, which is
            # exactly what verify_transaction_signature's keys.Signature(...) expects.
            signature = private_key.sign_msg_hash(keccak(_canonical_signing_message(transaction)))
            transaction["signature"] = signature.to_bytes().hex()

            self.logger.info("Generated signed transaction for %s to %s", amount, to_address)
            return transaction
        except Exception as e:
            self.logger.error("Error generating signed transaction: %s", e)
            return None
