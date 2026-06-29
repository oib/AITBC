"""Blockchain RPC client for Edge API Service"""

from typing import Any, cast

import httpx

from ..config import settings


class BlockchainRPCClient:
    """Client for blockchain node RPC communication"""

    def __init__(self) -> None:
        self.base_url = f"http://{settings.blockchain_rpc_host}:{settings.blockchain_rpc_port}"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()

    async def join_island(
        self, island_id: str, island_name: str, chain_id: str | list[str], role: str = "compute-provider", is_hub: bool = False
    ) -> dict[str, Any]:
        """Join island via blockchain RPC"""
        response = await self.client.post(
            f"{self.base_url}/rpc/islands/join",
            json={"island_id": island_id, "island_name": island_name, "chain_id": chain_id, "role": role, "is_hub": is_hub},
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def leave_island(self, island_id: str) -> dict[str, Any]:
        """Leave island via blockchain RPC"""
        response = await self.client.post(f"{self.base_url}/rpc/islands/leave", json={"island_id": island_id})
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def get_island_info(self, island_id: str) -> dict[str, Any] | None:
        """Get island info via blockchain RPC"""
        response = await self.client.get(f"{self.base_url}/rpc/islands/{island_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def list_islands(self) -> dict[str, Any]:
        """List all islands via blockchain RPC"""
        response = await self.client.get(f"{self.base_url}/rpc/islands")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def request_bridge(self, target_island_id: str) -> dict[str, Any]:
        """Request bridge via blockchain RPC"""
        response = await self.client.post(f"{self.base_url}/rpc/islands/bridge", json={"target_island_id": target_island_id})
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
