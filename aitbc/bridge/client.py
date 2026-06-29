"""Bridge RPC client for cross-chain operations (v0.7.0 §A1).

HTTP client that wraps the blockchain-node bridge RPC endpoints.
Used by the CLI and other services to interact with the bridge.

The client is async-first (httpx.AsyncClient) and supports both
context-manager usage (``async with BridgeClient() as c: ...``) and
explicit ``close()``. Methods raise ``httpx.HTTPStatusError`` on non-2xx
responses; callers are responsible for retry/backoff (the
``BridgeConfig.retry_limit`` is exposed for that purpose but not applied
automatically — keeping the client thin and predictable).
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from .types import BridgeConfig, BridgeStatus, BridgeTransfer

logger = logging.getLogger(__name__)


class BridgeClient:
    """HTTP client for blockchain-node bridge RPC endpoints.

    Wraps the following endpoints:
    - POST /bridge/lock — lock funds for cross-chain transfer
    - POST /bridge/confirm — confirm and release bridged funds
    - POST /bridge/unlock — refund/cancel a pending transfer
    - GET /bridge/transfer/{transfer_id} — get transfer status
    - GET /bridge/pending — list pending transfers
    - GET /bridge/balance/{chain_id} — get bridge balance per chain
    - GET /bridge/health — bridge health check
    - POST /bridge/batch/lock — batch lock
    - POST /bridge/batch/confirm — batch confirm
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._config = config or BridgeConfig()
        self._client: httpx.AsyncClient | None = None

    @property
    def config(self) -> BridgeConfig:
        """The active bridge configuration."""
        return self._config

    async def __aenter__(self) -> BridgeClient:
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

    async def lock(
        self,
        target_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        asset: str = "native",
        signature: str = "",
        source_chain: str | None = None,
    ) -> dict[str, Any]:
        """Lock funds for a cross-chain transfer."""
        payload: dict[str, Any] = {
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "asset": asset,
            "signature": signature,
        }
        if source_chain:
            payload["source_chain"] = source_chain
        resp = await self._ensure_client().post("/bridge/lock", json=payload)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def confirm(
        self,
        transfer_id: str,
        proof: dict[str, Any],
        confirmer: str,
        signature: str,
    ) -> dict[str, Any]:
        """Confirm and release a bridged transfer."""
        payload = {
            "transfer_id": transfer_id,
            "proof": proof,
            "confirmer": confirmer,
            "signature": signature,
        }
        resp = await self._ensure_client().post("/bridge/confirm", json=payload)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def unlock(
        self,
        transfer_id: str,
        sender: str,
        signature: str,
    ) -> dict[str, Any]:
        """Refund/cancel a pending bridge transfer."""
        payload = {
            "transfer_id": transfer_id,
            "sender": sender,
            "signature": signature,
        }
        resp = await self._ensure_client().post("/bridge/unlock", json=payload)
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Get transfer status by ID."""
        resp = await self._ensure_client().get(f"/bridge/transfer/{transfer_id}")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def list_pending(self, chain_id: str | None = None) -> list[dict[str, Any]]:
        """List pending bridge transfers."""
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        resp = await self._ensure_client().get("/bridge/pending", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        # Some servers wrap in {"transfers": [...]}
        if isinstance(data, dict) and isinstance(data.get("transfers"), list):
            return cast(list[dict[str, Any]], data["transfers"])
        return []

    async def get_balance(self, chain_id: str) -> dict[str, Any]:
        """Get bridge balance for a chain."""
        resp = await self._ensure_client().get(f"/bridge/balance/{chain_id}")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def health(self) -> dict[str, Any]:
        """Check bridge health."""
        resp = await self._ensure_client().get("/bridge/health")
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())

    async def batch_lock(
        self,
        transfers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch lock multiple transfers."""
        resp = await self._ensure_client().post("/bridge/batch/lock", json={"transfers": transfers})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return cast(list[dict[str, Any]], data["results"])
        return []

    async def batch_confirm(
        self,
        confirmations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch confirm multiple transfers."""
        resp = await self._ensure_client().post("/bridge/batch/confirm", json={"confirmations": confirmations})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return cast(list[dict[str, Any]], data["results"])
        return []

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


def transfer_from_dict(data: dict[str, Any]) -> BridgeTransfer:
    """Parse a BridgeTransfer from an RPC response dict.

    Tolerant of missing optional fields and string-or-enum status values.
    """
    raw_status = data.get("status", "pending")
    try:
        status = BridgeStatus(str(raw_status).lower())
    except ValueError:
        status = BridgeStatus.PENDING

    def _opt(key: str) -> str | None:
        v = data.get(key)
        return v if isinstance(v, str) and v else None

    return BridgeTransfer(
        transfer_id=data["transfer_id"],
        source_chain=data["source_chain"],
        target_chain=data["target_chain"],
        sender=data["sender"],
        recipient=data["recipient"],
        amount=int(data["amount"]),
        asset=data.get("asset", "native"),
        status=status,
        source_tx_hash=_opt("source_tx_hash"),
        target_tx_hash=_opt("target_tx_hash"),
        fee=int(data.get("fee", 0)),
    )
