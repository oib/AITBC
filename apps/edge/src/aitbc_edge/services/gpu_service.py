"""GPU service for Edge API Service"""

from typing import Any

from aitbc.aitbc_logging import get_logger

from ..clients.gpu_service import GPUServiceClient
from ..config import settings
from ..schemas.gpu import GPUListing
from ..storage import get_session

logger = get_logger(__name__)


class GPUService:
    """Service for GPU operations"""

    def __init__(self) -> None:
        self.gpu_client = GPUServiceClient()

    async def list_gpus(
        self, architecture: str | None = None, edge_optimized: bool | None = None, min_memory_gb: int | None = None
    ) -> list[dict[str, Any]]:
        """List GPUs via GPU service"""
        profiles = await self.gpu_client.get_gpu_profiles(architecture, edge_optimized, min_memory_gb)

        # Store GPU listings in edge-api database
        async with get_session() as session:
            for profile in profiles:
                gpu_listing = GPUListing(
                    gpu_id=profile.get("id", ""),
                    model=profile.get("model", "Unknown"),
                    price_per_hour=0.0,
                    memory_gb=profile.get("memory_gb", 0),
                    cuda_version=profile.get("cuda_version", ""),
                    region=profile.get("region", ""),
                    capabilities=profile.get("capabilities", []),
                    extra_data=profile,
                )
                session.add(gpu_listing)
            await session.commit()

        return profiles

    async def get_gpu_listing(self, gpu_id: str) -> dict[str, Any] | None:
        """Get GPU listing details"""
        # Get from GPU service
        try:
            profiles = await self.gpu_client.get_gpu_profiles()
            for profile in profiles:
                if profile.get("id") == gpu_id:
                    return profile
            return None
        except Exception:
            # Fall back to database
            from sqlmodel import select

            async with get_session() as session:
                result = await session.execute(select(GPUListing).where(GPUListing.gpu_id == gpu_id))
                gpu = result.scalar_one_or_none()
                if gpu:
                    return {
                        "id": gpu.gpu_id,
                        "model": gpu.model,
                        "memory_gb": gpu.memory_gb,
                        "cuda_version": gpu.cuda_version,
                        "region": gpu.region,
                        "capabilities": gpu.capabilities,
                        "extra_data": gpu.extra_data,
                    }
            return None

    async def remove_gpu_listing(self, gpu_id: str) -> bool:
        """Remove GPU listing from database"""
        from sqlmodel import delete

        async with get_session() as session:
            stmt = delete(GPUListing).where(GPUListing.gpu_id == gpu_id)  # type: ignore[arg-type]
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def scan_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan GPUs via GPU service"""
        result = await self.gpu_client.scan_gpus(miner_id)
        return result

    async def get_gpu_metrics(self, gpu_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get GPU metrics via GPU service"""
        metrics = await self.gpu_client.get_gpu_metrics(gpu_id, limit)
        return metrics

    async def advertise_to_marketplace(self) -> dict[str, Any]:
        """Advertise this edge node's GPU capabilities to the marketplace (v0.6.6).

        POSTs the list of available GPU profiles to the marketplace service so
        that the marketplace can include edge-hosted GPUs in offer discovery.
        """
        import httpx

        profiles = await self.gpu_client.get_gpu_profiles()
        payload = {
            "node_type": "edge",
            "service": "aitbc-edge",
            "gpu_count": len(profiles),
            "gpus": [
                {
                    "model": p.get("model", "Unknown"),
                    "memory_gb": p.get("memory_gb", 0),
                    "region": p.get("region", ""),
                    "capabilities": p.get("capabilities", []),
                }
                for p in profiles
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{settings.marketplace_url}/v1/marketplace/edge-advertise", json=payload)
                resp.raise_for_status()
                return {"status": "advertised", "gpu_count": len(profiles), "response": resp.json()}
        except Exception as e:
            logger.warning("Failed to advertise to marketplace: %s", e)
            return {"status": "failed", "error": str(e), "gpu_count": len(profiles)}
