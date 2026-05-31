"""GPU service client for Edge API Service"""

from typing import Any

import httpx

from ..config import settings


class GPUServiceClient:
    """Client for GPU service communication"""

    def __init__(self):
        self.base_url = f"http://{settings.gpu_service_host}:{settings.gpu_service_port}"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    async def scan_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan GPUs via GPU service"""
        response = await self.client.post(f"{self.base_url}/v1/marketplace/edge-gpu/scan/{miner_id}")
        response.raise_for_status()
        return response.json()

    async def get_gpu_profiles(self, architecture: str = None, edge_optimized: bool = None, min_memory_gb: int = None) -> list[dict[str, Any]]:
        """Get GPU profiles via GPU service"""
        params = {}
        if architecture:
            params["architecture"] = architecture
        if edge_optimized is not None:
            params["edge_optimized"] = edge_optimized
        if min_memory_gb is not None:
            params["min_memory_gb"] = min_memory_gb

        response = await self.client.get(f"{self.base_url}/v1/marketplace/edge-gpu/profiles", params=params)
        response.raise_for_status()
        return response.json()

    async def get_gpu_metrics(self, gpu_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get GPU metrics via GPU service"""
        response = await self.client.get(f"{self.base_url}/v1/marketplace/edge-gpu/metrics/{gpu_id}", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def get_miner_gpus(self, miner_id: str) -> list[dict[str, Any]]:
        """Get GPUs registered by a miner"""
        response = await self.client.get(f"{self.base_url}/v1/miners/{miner_id}/gpus")
        response.raise_for_status()
        return response.json()
