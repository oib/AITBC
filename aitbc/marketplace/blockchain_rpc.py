"""Chain-aware blockchain RPC client for marketplace operations (v0.6.6 §A2).

Provides a thin async HTTP client wrapping the blockchain node's RPC API
with chain_id-aware methods for:
- Querying GPU offers from the blockchain (GET /rpc/gpus)
- Getting a single GPU offer by ID (GET /rpc/gpu/info/{gpu_id})
- Submitting transactions with chain_id (POST /rpc/transaction)
- Registering GPUs on-chain (POST /rpc/gpu/register)
- Allocating GPUs on-chain (POST /rpc/gpu/allocate)
- Verifying escrow status (GET /rpc/escrow/{escrow_id})

Uses httpx.AsyncClient directly. Retry/circuit-breaker can be layered on
top by wiring in ``aitbc.network.client.AsyncAITBCHTTPClient`` in a future
release; for v0.6.6 we keep the dependency surface minimal.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


class BlockchainRPCClient:
    """Chain-aware blockchain RPC client for marketplace operations.

    Wraps httpx.AsyncClient with chain_id-aware methods for offer queries,
    transaction submission, GPU registration/allocation, and escrow verification.
    """

    def __init__(self, rpc_url: str = "http://localhost:8202", timeout: float = 10.0) -> None:
        self._rpc_url = rpc_url.rstrip("/")
        self._timeout = timeout

    @property
    def rpc_url(self) -> str:
        """Base RPC URL (no trailing slash)."""
        return self._rpc_url

    async def query_offers(
        self,
        chain_id: str | None = None,
        status: str | None = None,
        gpu_model: str | None = None,
        region: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Query GPU offers from blockchain.

        Calls GET /rpc/gpus with optional chain_id and status filters.
        gpu_model and region are filtered client-side (blockchain RPC
        does not yet support them as query params).
        Returns list of offer dicts.
        """
        params: dict[str, Any] = {"limit": limit}
        if chain_id:
            params["chain_id"] = chain_id
        if status:
            params["status"] = status
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/gpus", params=params)
            resp.raise_for_status()
            data = resp.json()
        offers = data.get("gpus", data) if isinstance(data, dict) else data
        if not isinstance(offers, list):
            offers = []
        # Client-side filter for gpu_model and region
        if gpu_model:
            offers = [o for o in offers if gpu_model.lower() in str(o.get("model", "")).lower()]
        if region:
            offers = [o for o in offers if region.lower() in str(o.get("region", "")).lower()]
        return offers

    async def get_offer(self, gpu_id: str, chain_id: str | None = None) -> dict[str, Any] | None:
        """Get a single GPU offer by ID.

        Returns None if the offer is not found (404).
        """
        params: dict[str, Any] = {}
        if chain_id:
            params["chain_id"] = chain_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/gpu/info/{gpu_id}", params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    async def submit_transaction(self, tx_data: dict[str, Any]) -> dict[str, Any]:
        """Submit a transaction to the blockchain.

        The tx_data must include ``chain_id``. Calls POST /rpc/transaction.
        Returns the blockchain response dict.
        """
        if not tx_data.get("chain_id"):
            raise ValueError("tx_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/transaction", json=tx_data)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    async def verify_escrow(self, escrow_id: str) -> dict[str, Any] | None:
        """Verify escrow status on blockchain.

        Calls GET /rpc/escrow/{escrow_id}. Returns None if not found (404).
        For v0.6.6, escrow verification may also go through the agent-coordinator's
        escrow endpoint — this method provides direct blockchain verification.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._rpc_url}/rpc/escrow/{escrow_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return cast(dict[str, Any] | None, resp.json())

    async def register_gpu(self, registration_data: dict[str, Any]) -> dict[str, Any]:
        """Register a GPU on the blockchain.

        Calls POST /rpc/gpu/register. The registration_data must include ``chain_id``.
        """
        if not registration_data.get("chain_id"):
            raise ValueError("registration_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/gpu/register", json=registration_data)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())

    async def allocate_gpu(self, allocation_data: dict[str, Any]) -> dict[str, Any]:
        """Allocate a GPU on the blockchain (record a booking).

        Calls POST /rpc/gpu/allocate. The allocation_data must include ``chain_id``.
        """
        if not allocation_data.get("chain_id"):
            raise ValueError("allocation_data must include 'chain_id'")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._rpc_url}/rpc/gpu/allocate", json=allocation_data)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())
