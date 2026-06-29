"""Trading service RPC client (v0.8.0 §A2).

Async HTTP client that wraps the trading service REST endpoints
(``apps/trading/src/trading_service/main.py``). Used by the CLI and
other services to create inter-chain trades, list chains, query trade
status, and view trade history.

The client is async-first (``httpx.AsyncClient``) and supports both
context-manager usage (``async with TradingClient() as c: ...``) and
explicit ``close()``. Methods raise ``httpx.HTTPStatusError`` on non-2xx
responses; callers are responsible for retry/backoff.

Endpoint mapping (Agent B B4-B5 will add these to main.py):
- POST /v1/trading/inter-chain/create       -> create_trade
- GET  /v1/trading/inter-chain              -> list_trades
- GET  /v1/trading/inter-chain/{trade_id}   -> get_trade
- GET  /v1/trading/inter-chain/{trade_id}/status -> get_trade_status
- GET  /v1/trading/inter-chain/history      -> get_trade_history
- GET  /v1/trading/chains                   -> list_chains
- POST /v1/trading/chains/register          -> register_chain
- GET  /v1/trading/chains/{chain_id}/health -> get_chain_health
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from .types import TradingConfig

logger = logging.getLogger(__name__)


class TradingClient:
    """HTTP client for the trading service REST endpoints.

    Wraps the trading service API (``apps/trading/``) for creating
    inter-chain trades, listing chains, querying trade status, and
    viewing trade history. The trading service runs on port 8104 by
    default (``TRADING_BIND_PORT``, verified in ``main.py:469``).
    """

    def __init__(self, config: TradingConfig | None = None) -> None:
        self._config = config or TradingConfig()
        self._client: httpx.AsyncClient | None = None

    @property
    def config(self) -> TradingConfig:
        """The active trading configuration."""
        return self._config

    async def __aenter__(self) -> TradingClient:
        self._client = httpx.AsyncClient(
            base_url=self._config.rpc_url,
            timeout=self._config.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.rpc_url,
                timeout=self._config.timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Inter-chain trades
    # ------------------------------------------------------------------

    async def create_trade(self, trade_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new inter-chain trade.

        ``trade_data`` should contain: source_chain, dest_chain, sender,
        recipient, amount, offer_id (optional), price, quantity. The
        trading service will create an InterChainTrade record and return
        the trade_id.
        """
        resp = await self._ensure_client().post("/v1/trading/inter-chain/create", json=trade_data)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_trade(self, trade_id: str) -> dict[str, Any]:
        """Get an inter-chain trade by ID."""
        resp = await self._ensure_client().get(f"/v1/trading/inter-chain/{trade_id}")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def list_trades(
        self,
        status: str | None = None,
        source_chain: str | None = None,
        dest_chain: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List inter-chain trades with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if source_chain:
            params["source_chain"] = source_chain
        if dest_chain:
            params["dest_chain"] = dest_chain
        resp = await self._ensure_client().get("/v1/trading/inter-chain", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        if isinstance(data, dict) and isinstance(data.get("trades"), list):
            return cast(list[dict[str, Any]], data["trades"])
        return []

    async def get_trade_status(self, trade_id: str) -> dict[str, Any]:
        """Get the status of an inter-chain trade."""
        resp = await self._ensure_client().get(f"/v1/trading/inter-chain/{trade_id}/status")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_trade_history(
        self,
        source_chain: str | None = None,
        dest_chain: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get inter-chain trade history with optional chain filters."""
        params: dict[str, Any] = {"limit": limit}
        if source_chain:
            params["source_chain"] = source_chain
        if dest_chain:
            params["dest_chain"] = dest_chain
        resp = await self._ensure_client().get("/v1/trading/inter-chain/history", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        if isinstance(data, dict) and isinstance(data.get("history"), list):
            return cast(list[dict[str, Any]], data["history"])
        return []

    # ------------------------------------------------------------------
    # Chain registry / discovery
    # ------------------------------------------------------------------

    async def list_chains(self) -> list[dict[str, Any]]:
        """List all registered AITBC chains."""
        resp = await self._ensure_client().get("/v1/trading/chains")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        if isinstance(data, dict) and isinstance(data.get("chains"), list):
            return cast(list[dict[str, Any]], data["chains"])
        return []

    async def register_chain(self, chain_id: str, endpoint: str) -> dict[str, Any]:
        """Register a new chain in the island registry."""
        payload = {"chain_id": chain_id, "endpoint": endpoint}
        resp = await self._ensure_client().post("/v1/trading/chains/register", json=payload)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_chain_health(self, chain_id: str) -> dict[str, Any]:
        """Get health status for a registered chain."""
        resp = await self._ensure_client().get(f"/v1/trading/chains/{chain_id}/health")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Check trading service health."""
        resp = await self._ensure_client().get("/health")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
