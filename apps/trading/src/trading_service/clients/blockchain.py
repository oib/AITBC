"""Blockchain RPC client for the trading service (v0.8.0 §B3).

Provides an async HTTP client wrapping the blockchain node's RPC API
for chain health queries, block height, and account balance lookups.
Used by the chain discovery service (B4) to monitor registered chains.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


class BlockchainClient:
    """Async blockchain RPC client for trading service operations."""

    def __init__(self, rpc_url: str = "http://localhost:8202", timeout: float = 10.0) -> None:
        self._rpc_url = rpc_url.rstrip("/")
        self._timeout = timeout

    @property
    def rpc_url(self) -> str:
        return self._rpc_url

    async def get_chain_health(self, chain_id: str | None = None) -> dict[str, Any]:
        """Get chain health metrics.

        Calls GET /rpc/info which returns comprehensive blockchain info.
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/info", params=params)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    async def get_block_height(self, chain_id: str | None = None) -> int:
        """Get the current block height for a chain."""
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._rpc_url}/rpc/height", params=params)
                resp.raise_for_status()
                data = cast(dict[str, Any], resp.json())
            return int(data.get("height", 0))
        except Exception as e:
            logger.warning("Failed to get block height: %s", e)
            return 0

    async def get_account_balance(self, address: str, chain_id: str | None = None) -> int:
        """Get the on-chain balance for an address."""
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
            return int(data.get("balance", 0))
        except Exception as e:
            logger.warning("Failed to get balance for %s: %s", address, e)
            return 0
