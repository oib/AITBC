"""
Edge API Client for Agent SDK
Provides access to Edge API endpoints for agents
"""

from dataclasses import dataclass
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class EdgeAPIConfig:
    """Edge API configuration"""
    host: str = "localhost"
    port: int = 8103
    timeout: int = 30


class EdgeAPIClient:
    """Client for interacting with Edge API"""

    def __init__(self, config: EdgeAPIConfig | None = None) -> None:
        self.config = config or EdgeAPIConfig()
        self.base_url = f"http://{self.config.host}:{self.config.port}"
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EdgeAPIClient":
        """Async context manager entry"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.config.timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()

    # GPU Operations
    async def list_gpus(
        self,
        architecture: str | None = None,
        edge_optimized: bool = False,
        min_memory_gb: int | None = None
    ) -> list[dict[str, Any]]:
        """List available GPUs"""
        params = {}
        if architecture:
            params["architecture"] = architecture
        if edge_optimized:
            params["edge_optimized"] = edge_optimized
        if min_memory_gb:
            params["min_memory_gb"] = min_memory_gb

        response = await self._client.get("/v1/gpu/", params=params)
        response.raise_for_status()
        result = response.json()
        return result.get("gpus", [])

    async def get_gpu(self, gpu_id: str) -> dict[str, Any]:
        """Get GPU details"""
        response = await self._client.get(f"/v1/gpu/{gpu_id}")
        response.raise_for_status()
        return response.json()

    async def scan_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan GPUs for a miner"""
        response = await self._client.post("/v1/gpu/scan", json={"miner_id": miner_id})
        response.raise_for_status()
        return response.json()

    async def get_gpu_metrics(self, gpu_id: str, limit: int = 100) -> dict[str, Any]:
        """Get GPU metrics"""
        response = await self._client.get(
            f"/v1/gpu/{gpu_id}/metrics",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()

    async def remove_gpu(self, gpu_id: str) -> dict[str, Any]:
        """Remove GPU from listing"""
        response = await self._client.delete(f"/v1/gpu/{gpu_id}")
        response.raise_for_status()
        return response.json()

    # Database Operations
    async def init_database(
        self,
        database_id: str,
        island_id: str,
        capacity_gb: int
    ) -> dict[str, Any]:
        """Initialize edge database"""
        response = await self._client.post("/v1/database/init", json={
            "database_id": database_id,
            "island_id": island_id,
            "capacity_gb": capacity_gb
        })
        response.raise_for_status()
        return response.json()

    async def list_databases(self, island_id: str | None = None) -> list[dict[str, Any]]:
        """List edge databases"""
        params = {}
        if island_id:
            params["island_id"] = island_id

        response = await self._client.get("/v1/database/", params=params)
        response.raise_for_status()
        result = response.json()
        return result.get("databases", [])

    async def get_database(self, database_id: str) -> dict[str, Any]:
        """Get database details"""
        response = await self._client.get(f"/v1/database/{database_id}")
        response.raise_for_status()
        return response.json()

    async def delete_database(self, database_id: str) -> dict[str, Any]:
        """Delete database"""
        response = await self._client.delete(f"/v1/database/{database_id}")
        response.raise_for_status()
        return response.json()

    async def sync_database(self, database_id: str) -> dict[str, Any]:
        """Sync database"""
        response = await self._client.post(f"/v1/database/{database_id}/sync")
        response.raise_for_status()
        return response.json()

    # Serve Operations
    async def submit_compute_request(
        self,
        gpu_id: str,
        model_name: str,
        input_data: dict[str, Any],
        priority: str = "normal"
    ) -> dict[str, Any]:
        """Submit compute request"""
        response = await self._client.post("/v1/serve/requests", json={
            "gpu_id": gpu_id,
            "model_name": model_name,
            "input_data": input_data,
            "priority": priority
        })
        response.raise_for_status()
        return response.json()

    async def list_compute_requests(
        self,
        gpu_id: str | None = None,
        status: str | None = None
    ) -> list[dict[str, Any]]:
        """List compute requests"""
        params = {}
        if gpu_id:
            params["gpu_id"] = gpu_id
        if status:
            params["status"] = status

        response = await self._client.get("/v1/serve/requests", params=params)
        response.raise_for_status()
        result = response.json()
        return result.get("requests", [])

    async def get_compute_request(self, request_id: str) -> dict[str, Any]:
        """Get compute request details"""
        response = await self._client.get(f"/v1/serve/requests/{request_id}")
        response.raise_for_status()
        return response.json()

    async def cancel_compute_request(self, request_id: str) -> dict[str, Any]:
        """Cancel compute request"""
        response = await self._client.post(f"/v1/serve/requests/{request_id}/cancel")
        response.raise_for_status()
        return response.json()

    async def get_compute_result(self, request_id: str) -> dict[str, Any]:
        """Get compute result"""
        response = await self._client.get(f"/v1/serve/requests/{request_id}/result")
        response.raise_for_status()
        return response.json()

    # Metrics Operations
    async def record_metrics(
        self,
        gpu_id: str,
        metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """Record edge metrics"""
        response = await self._client.post("/v1/metrics/", json={
            "gpu_id": gpu_id,
            "metrics": metrics
        })
        response.raise_for_status()
        return response.json()

    async def list_metrics(
        self,
        gpu_id: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """List edge metrics"""
        params = {"limit": limit}
        if gpu_id:
            params["gpu_id"] = gpu_id

        response = await self._client.get("/v1/metrics/", params=params)
        response.raise_for_status()
        result = response.json()
        return result.get("metrics", [])

    async def get_metric(self, metric_id: str) -> dict[str, Any]:
        """Get metric details"""
        response = await self._client.get(f"/v1/metrics/{metric_id}")
        response.raise_for_status()
        return response.json()

    async def delete_metric(self, metric_id: str) -> dict[str, Any]:
        """Delete metric"""
        response = await self._client.delete(f"/v1/metrics/{metric_id}")
        response.raise_for_status()
        return response.json()

    # Island Operations
    async def join_island(
        self,
        island_id: str,
        island_name: str,
        chain_id: str,
        role: str = "compute-provider",
        is_hub: bool = False
    ) -> dict[str, Any]:
        """Join an island"""
        response = await self._client.post("/v1/islands/join", json={
            "island_id": island_id,
            "island_name": island_name,
            "chain_id": chain_id,
            "role": role,
            "is_hub": is_hub
        })
        response.raise_for_status()
        return response.json()

    async def leave_island(self, island_id: str) -> dict[str, Any]:
        """Leave an island"""
        response = await self._client.post("/v1/islands/leave", json={
            "island_id": island_id
        })
        response.raise_for_status()
        return response.json()

    async def list_islands(self) -> list[dict[str, Any]]:
        """List all islands"""
        response = await self._client.get("/v1/islands/")
        response.raise_for_status()
        result = response.json()
        return result.get("islands", [])

    async def get_island(self, island_id: str) -> dict[str, Any]:
        """Get island details"""
        response = await self._client.get(f"/v1/islands/{island_id}")
        response.raise_for_status()
        return response.json()

    async def request_bridge(self, target_island_id: str) -> dict[str, Any]:
        """Request bridge to another island"""
        response = await self._client.post("/v1/islands/bridge", json={
            "target_island_id": target_island_id
        })
        response.raise_for_status()
        return response.json()
