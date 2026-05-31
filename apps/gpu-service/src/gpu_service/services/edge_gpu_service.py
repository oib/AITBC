"""
Edge GPU service for managing GPU operations
"""

from typing import Any

from sqlmodel import Session, select

from aitbc import get_logger

from ..data.consumer_gpu_profiles import CONSUMER_GPU_PROFILES
from ..domain.gpu_marketplace import ConsumerGPUProfile, EdgeGPUMetrics, GPUArchitecture, GPURegistry

logger = get_logger(__name__)


class EdgeGPUService:
    def __init__(self, session: Session):
        self.session = session

    async def list_profiles(
        self,
        architecture: GPUArchitecture | None = None,
        edge_optimized: bool | None = None,
        min_memory_gb: int | None = None,
    ) -> list[ConsumerGPUProfile]:
        """List consumer GPU profiles with optional filters"""
        try:
            self.seed_profiles()
            stmt = select(ConsumerGPUProfile)
            if architecture:
                stmt = stmt.where(ConsumerGPUProfile.architecture == architecture)
            if edge_optimized is not None:
                stmt = stmt.where(ConsumerGPUProfile.edge_optimized == edge_optimized)
            if min_memory_gb is not None:
                stmt = stmt.where(ConsumerGPUProfile.memory_gb >= min_memory_gb)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to list GPU profiles: {e}")
            return []

    async def list_metrics(self, gpu_id: str, limit: int = 100) -> list[EdgeGPUMetrics]:
        """List edge GPU metrics for a specific GPU"""
        try:
            stmt = (
                select(EdgeGPUMetrics)
                .where(EdgeGPUMetrics.gpu_id == gpu_id)
                .order_by(EdgeGPUMetrics.timestamp.desc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to list GPU metrics for {gpu_id}: {e}")
            return []

    def create_metric(self, payload: dict) -> EdgeGPUMetrics:
        metric = EdgeGPUMetrics(**payload)
        self.session.add(metric)
        self.session.commit()
        self.session.refresh(metric)
        return metric

    async def seed_profiles(self) -> None:
        """Seed consumer GPU profiles into database"""
        try:
            result = await self.session.execute(select(ConsumerGPUProfile.gpu_model))
            existing_models = {row[0] for row in result.all()}
            created = 0
            for profile in CONSUMER_GPU_PROFILES.values():
                if profile["gpu_model"] in existing_models:
                    continue
                self.session.add(ConsumerGPUProfile(**profile))
                created += 1
            if created:
                await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.warning(f"Failed to seed GPU profiles: {e}")

    async def discover_and_register_edge_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan and register edge GPUs for a miner"""
        try:
            # Query existing GPUs from GPURegistry for this miner
            stmt = select(GPURegistry).where(GPURegistry.miner_id == miner_id)
            result = await self.session.execute(stmt)
            gpus = result.scalars().all()

            # Count edge-optimized GPUs (those with edge-related capabilities)
            edge_optimized_count = 0
            gpu_list = []
            for gpu in gpus:
                gpu_list.append({
                    "id": gpu.id,
                    "model": gpu.model,
                    "memory_gb": gpu.memory_gb,
                    "region": gpu.region,
                    "status": gpu.status,
                    "capabilities": gpu.capabilities
                })
                # Check if GPU has edge-related capabilities
                if any("edge" in str(cap).lower() or "inference" in str(cap).lower() for cap in gpu.capabilities):
                    edge_optimized_count += 1

            return {
                "miner_id": miner_id,
                "gpus": gpu_list,
                "registered": len(gpu_list),
                "edge_optimized": edge_optimized_count,
            }
        except Exception as e:
            logger.error(f"Failed to discover GPUs for miner {miner_id}: {e}")
            return {
                "miner_id": miner_id,
                "gpus": [],
                "registered": 0,
                "edge_optimized": 0,
                "error": str(e)
            }

    async def optimize_inference_for_edge(self, gpu_id: str, model_name: str, request_data: dict) -> dict[str, Any]:
        """Optimize ML inference request for edge GPU"""
        # Placeholder for inference optimization logic
        return {
            "gpu_id": gpu_id,
            "model_name": model_name,
            "optimized": True,
            "latency_reduction": 0.0,
        }
