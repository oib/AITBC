"""Shared blockchain RPC client (v0.10.7 §B2).

Provides a reusable async HTTP client wrapping the blockchain node's RPC API
with chain_id-aware methods for:
- Querying block height (GET /rpc/height)
- Querying account balance (GET /rpc/account/{address})
- Querying chain health (GET /rpc/info)
- Submitting transactions (POST /rpc/transaction)
- Fetching nonces (GET /rpc/account/{address})

Uses a shared ``httpx.AsyncClient`` instance to avoid per-request
TCP+TLS handshake overhead. The client is lazily created on first
use and must be closed via ``aclose()`` during service shutdown.

Services requiring additional functionality (e.g. governance transaction
signing) should subclass ``BlockchainClient`` and add their specific methods.
"""

from __future__ import annotations

from aitbc.constants import BLOCKCHAIN_RPC_URL
from decimal import Decimal

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


class BlockchainClient:
    """Async blockchain RPC client with a shared lazy ``httpx.AsyncClient``.

    The shared client avoids per-request TCP+TLS handshake overhead. It is
    lazily created on first use and must be closed via ``aclose()`` during
    service shutdown.
    """

    def __init__(self, rpc_url: str = BLOCKCHAIN_RPC_URL, timeout: float = 10.0) -> None:
        self._rpc_url = rpc_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """Close the shared HTTP client. Call during service shutdown."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @property
    def rpc_url(self) -> str:
        """Base RPC URL (no trailing slash)."""
        return self._rpc_url

    async def get_chain_health(self, chain_id: str | None = None) -> dict[str, Any]:
        """Get chain health metrics.

        Calls GET /rpc/info which returns comprehensive blockchain info.
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        client = self._ensure_client()
        resp = await client.get(f"{self._rpc_url}/rpc/info", params=params)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_block_height(self, chain_id: str | None = None) -> int:
        """Get the current block height for a chain.

        Calls GET /rpc/height. Returns 0 if the chain is empty.
        Raises ``httpx.HTTPStatusError`` if the node is unreachable.
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        client = self._ensure_client()
        resp = await client.get(f"{self._rpc_url}/rpc/height", params=params)
        resp.raise_for_status()
        data = cast(dict[str, Any], resp.json())
        return int(data.get("height", 0))

    async def get_balance(self, address: str, chain_id: str | None = None) -> Decimal:
        """Get the on-chain balance for an address.

        Calls GET /rpc/account/{address}. Returns 0.0 if the account
        is not found (new accounts have zero balance).
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        client = self._ensure_client()
        resp = await client.get(f"{self._rpc_url}/rpc/account/{address}", params=params)
        if resp.status_code == 404:
            return Decimal("0.0")
        resp.raise_for_status()
        data = cast(dict[str, Any], resp.json())
        return Decimal(str(data.get("balance", 0.0)))

    async def get_account_balance(self, address: str, chain_id: str | None = None) -> int:
        """Get the on-chain balance for an address as an integer.

        Calls GET /rpc/account/{address}. Returns 0 if the account
        is not found. Logs and returns 0 on transient errors.
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        try:
            client = self._ensure_client()
            resp = await client.get(f"{self._rpc_url}/rpc/account/{address}", params=params)
            if resp.status_code == 404:
                return 0
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            return int(data.get("balance", 0))
        except Exception as e:
            logger.warning("Failed to get balance for %s: %s", address, e)
            return 0

    async def submit_transaction(self, tx_data: dict[str, Any]) -> dict[str, Any]:
        """Submit a transaction to the blockchain.

        The tx_data must include ``chain_id``. Calls POST /rpc/transaction.
        Returns the blockchain response dict (includes tx_hash, block_height, status).
        """
        if not tx_data.get("chain_id"):
            raise ValueError("tx_data must include 'chain_id'")
        client = self._ensure_client()
        resp = await client.post(f"{self._rpc_url}/rpc/transaction", json=tx_data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def _get_nonce(self, address: str, chain_id: str | None = None) -> int:
        """Get the current nonce for an address."""
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        try:
            client = self._ensure_client()
            resp = await client.get(f"{self._rpc_url}/rpc/account/{address}", params=params)
            if resp.status_code == 404:
                return 0
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            return int(data.get("nonce", 0))
        except Exception as e:
            logger.warning("Failed to get nonce for %s: %s — defaulting to 0", address, e)
            return 0
