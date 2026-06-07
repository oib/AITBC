"""GPU service for Edge API Service"""


from ..clients.gpu_service import GPUServiceClient
from ..schemas.gpu import GPUListing
from ..storage import get_session


class GPUService:
    """Service for GPU operations"""

    def __init__(self):
        self.gpu_client = GPUServiceClient()

    async def list_gpus(self, architecture: str = None, edge_optimized: bool = None, min_memory_gb: int = None) -> list[dict]:
        """List GPUs via GPU service"""
        profiles = await self.gpu_client.get_gpu_profiles(architecture, edge_optimized, min_memory_gb)

        # Store GPU listings in edge-api database
        async with get_session() as session:
            for profile in profiles:
                gpu_listing = GPUListing(
                    gpu_id=profile.get("id", ""),
                    model=profile.get("model", "Unknown"),
                    memory_gb=profile.get("memory_gb", 0),
                    cuda_version=profile.get("cuda_version", ""),
                    region=profile.get("region", ""),
                    capabilities=profile.get("capabilities", []),
                    extra_data=profile
                )
                session.add(gpu_listing)
            await session.commit()

        return profiles

    async def get_gpu_listing(self, gpu_id: str) -> dict | None:
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
                        "extra_data": gpu.extra_data
                    }
            return None

    async def remove_gpu_listing(self, gpu_id: str) -> bool:
        """Remove GPU listing from database"""
        from sqlmodel import delete
        async with get_session() as session:
            stmt = delete(GPUListing).where(GPUListing.gpu_id == gpu_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def scan_gpus(self, miner_id: str) -> dict:
        """Scan GPUs via GPU service"""
        result = await self.gpu_client.scan_gpus(miner_id)
        return result

    async def get_gpu_metrics(self, gpu_id: str, limit: int = 100) -> list[dict]:
        """Get GPU metrics via GPU service"""
        metrics = await self.gpu_client.get_gpu_metrics(gpu_id, limit)
        return metrics
