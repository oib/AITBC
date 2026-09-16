"""Blockchain RPC client for the governance service (v0.7.3 §B2, v0.10.7 §B2).

Extends the shared ``aitbc.blockchain.rpc_client.BlockchainClient`` with
governance-specific operations:
- Voting power queries (alias for get_balance)
- Governance transaction signing and submission (secp256k1 / Ethereum-style)

Governance transaction signing uses secp256k1 (Ethereum-style) over the
canonical JSON of the signed fields, matching the blockchain node's
verifier (see ``aitbc.crypto.transaction_service``).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from aitbc.blockchain.rpc_client import BlockchainClient as BaseBlockchainClient
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS

logger = logging.getLogger(__name__)

# Transaction fields covered by the signature — must match the node verifier.
_SIGNED_FIELDS = ("from", "to", "amount", "fee", "nonce", "payload", "type", "chain_id")


def _canonical_signing_message(tx: dict[str, Any]) -> bytes:
    """Return the exact bytes that are hashed and signed for a transaction.

    Must remain identical to the node verifier's reconstruction:
    ``json.dumps(<signed fields>, sort_keys=True, separators=(",", ":"))``.
    """
    signed = {k: tx[k] for k in _SIGNED_FIELDS if k in tx}
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()


class BlockchainClient(BaseBlockchainClient):
    """Async blockchain RPC client for governance operations.

    Extends the shared ``BlockchainClient`` with governance transaction
    signing (secp256k1) and voting power queries.
    """

    async def get_voting_power(self, address: str, chain_id: str | None = None) -> Decimal:
        """Get on-chain voting power (balance) for an address.

        This is the on-chain balance snapshot used for vote weight.
        Calls get_balance() under the hood.
        """
        return await self.get_balance(address, chain_id)

    async def submit_governance_tx(
        self,
        tx_type: str,
        sender: str,
        private_key: str,
        payload: dict[str, Any],
        chain_id: str = "ait-hub",
        nonce: int | None = None,
    ) -> dict[str, Any]:
        """Build, sign, and submit a governance transaction.

        Args:
            tx_type: GOVERNANCE_PROPOSE, GOVERNANCE_VOTE, or GOVERNANCE_EXECUTE
            sender: Sender address (must match the address derived from private_key)
            private_key: Hex-encoded secp256k1 private key
            payload: Governance-specific payload dict
            chain_id: Chain identifier
            nonce: Transaction nonce (auto-fetched if None)

        Returns:
            Blockchain response dict (includes tx_hash, block_height, status)

        Raises:
            ValueError: If private_key is empty or sender doesn't match key
            httpx.HTTPStatusError: If the blockchain rejects the transaction
        """
        if not private_key:
            raise ValueError("private_key is required to sign governance transactions")

        from eth_keys import keys
        from eth_utils import keccak

        pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
        derived_address = pk.public_key.to_checksum_address()
        if sender.lower() != derived_address.lower():
            raise ValueError(
                f"Sender address {sender} does not match the address derived from the private key ({derived_address})"
            )

        if nonce is None:
            nonce = await self._get_nonce(sender, chain_id)

        # TransactionRequest.validate_payload injects ``to``/``amount`` into
        # payload before signature verification. Sign the post-injection shape
        # or the recovered address never matches the sender.
        signed_payload = {"to": sender, "amount": 0, **payload}

        tx: dict[str, Any] = {
            "from": sender,
            "to": sender,  # Governance txs are self-directed (no value transfer)
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce,
            "payload": signed_payload,
            "type": tx_type,
            "chain_id": chain_id,
        }

        signature = pk.sign_msg_hash(keccak(_canonical_signing_message(tx)))
        tx["signature"] = signature.to_bytes().hex()

        return await self.submit_transaction(tx)

    async def submit_signed_governance_tx(self, signed_tx: dict[str, Any]) -> dict[str, Any]:
        """Relay a fully client-signed governance transaction.

        The caller's wallet signs off-service; this service never sees a
        private key. The signature is re-verified here (recover(signer) ==
        ``from`` == ``to``) so malformed or mis-signed txs fail with a
        ValueError instead of an opaque chain rejection. The node verifies
        again on admission — this check is defense-in-depth, not authority.

        Raises:
            ValueError: missing fields, malformed signature, signer mismatch,
                or a non-self-directed/non-zero-value transaction.
        """
        required = {"from", "to", "amount", "fee", "nonce", "payload", "type", "chain_id", "signature"}
        missing = required - set(signed_tx)
        if missing:
            raise ValueError(f"signed_tx missing fields: {sorted(missing)}")

        from aitbc.crypto.signature_recovery import recover_address
        from eth_utils import keccak

        digest = keccak(_canonical_signing_message(signed_tx))
        try:
            recovered = recover_address(digest, signed_tx["signature"])
        except Exception as exc:
            raise ValueError(f"signed_tx signature is malformed: {exc}") from exc

        sender = str(signed_tx["from"])
        if recovered.lower() != sender.lower():
            raise ValueError("signed_tx signature does not recover to 'from'")
        if str(signed_tx["to"]).lower() != sender.lower():
            raise ValueError("governance transactions must be self-directed (to must equal from)")
        if signed_tx["amount"] != 0:
            raise ValueError("governance transactions must carry amount=0")
        return await self.submit_transaction(signed_tx)
