"""Blockchain RPC client for the governance service (v0.7.3 §B2).

Provides an async HTTP client wrapping the blockchain node's RPC API
for governance operations:
- Query account balance (GET /rpc/account/{address}) — for voting power snapshots
- Submit transactions (POST /rpc/transaction) — for GOVERNANCE_* txs
- Get block height (GET /rpc/height) — for snapshot block determination

Uses httpx.AsyncClient directly, following the same pattern as
``aitbc.marketplace.blockchain_rpc.BlockchainRPCClient``.

Governance transaction signing uses secp256k1 (Ethereum-style) over the
canonical JSON of the signed fields, matching the blockchain node's
verifier (see ``aitbc.crypto.transaction_service``).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import httpx

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


class BlockchainClient:
    """Async blockchain RPC client for governance operations.

    Wraps httpx.AsyncClient with chain_id-aware methods for balance
    queries, transaction submission, and block height queries.
    """

    def __init__(self, rpc_url: str = "http://localhost:8202", timeout: float = 10.0) -> None:
        self._rpc_url = rpc_url.rstrip("/")
        self._timeout = timeout

    @property
    def rpc_url(self) -> str:
        """Base RPC URL (no trailing slash)."""
        return self._rpc_url

    async def get_balance(self, address: str, chain_id: str | None = None) -> float:
        """Get the on-chain balance for an address.

        Calls GET /rpc/account/{address}. Returns 0.0 if the account
        is not found (new accounts have zero balance).
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/account/{address}", params=params)
            if resp.status_code == 404:
                return 0.0
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
        return float(data.get("balance", 0.0))

    async def get_block_height(self, chain_id: str | None = None) -> int:
        """Get the current block height.

        Calls GET /rpc/height. Returns 0 if the chain is empty or unreachable.
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/height", params=params)
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
        return int(data.get("height", 0))

    async def submit_transaction(self, tx_data: dict[str, Any]) -> dict[str, Any]:
        """Submit a transaction to the blockchain.

        The tx_data must include ``chain_id``. Calls POST /rpc/transaction.
        Returns the blockchain response dict (includes tx_hash, block_height, status).
        """
        if not tx_data.get("chain_id"):
            raise ValueError("tx_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/transaction", json=tx_data)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    async def get_voting_power(self, address: str, chain_id: str | None = None) -> float:
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

        tx: dict[str, Any] = {
            "from": sender,
            "to": sender,  # Governance txs are self-directed (no value transfer)
            "amount": 0,
            "fee": 36,
            "nonce": nonce,
            "payload": payload,
            "type": tx_type,
            "chain_id": chain_id,
        }

        signature = pk.sign_msg_hash(keccak(_canonical_signing_message(tx)))
        tx["signature"] = signature.to_bytes().hex()

        return await self.submit_transaction(tx)

    async def _get_nonce(self, address: str, chain_id: str | None = None) -> int:
        """Get the current nonce for an address."""
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._rpc_url}/rpc/account/{address}", params=params)
                if resp.status_code == 404:
                    return 0
                resp.raise_for_status()
                data = cast(dict[str, Any], resp.json())
            return int(data.get("nonce", 0))
        except Exception as e:
            logger.warning("Failed to get nonce for %s: %s — defaulting to 0", address, e)
            return 0
