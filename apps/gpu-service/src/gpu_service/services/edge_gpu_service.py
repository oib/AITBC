"""
Edge GPU service for managing GPU operations
"""

from typing import Any

from sqlmodel import Session, select

from ..data.consumer_gpu_profiles import CONSUMER_GPU_PROFILES
from ..domain.gpu_marketplace import ConsumerGPUProfile, EdgeGPUMetrics, GPUArchitecture


class EdgeGPUService:
    def __init__(self, session: Session):
        self.session = session

    def list_profiles(
        self,
        architecture: GPUArchitecture | None = None,
        edge_optimized: bool | None = None,
        min_memory_gb: int | None = None,
    ) -> list[ConsumerGPUProfile]:
        self.seed_profiles()
        stmt = select(ConsumerGPUProfile)
        if architecture:
            stmt = stmt.where(ConsumerGPUProfile.architecture == architecture)
        if edge_optimized is not None:
            stmt = stmt.where(ConsumerGPUProfile.edge_optimized == edge_optimized)
        if min_memory_gb is not None:
            stmt = stmt.where(ConsumerGPUProfile.memory_gb >= min_memory_gb)
        return list(self.session.execute(stmt).all())

    def list_metrics(self, gpu_id: str, limit: int = 100) -> list[EdgeGPUMetrics]:
        stmt = (
            select(EdgeGPUMetrics)
            .where(EdgeGPUMetrics.gpu_id == gpu_id)
            .order_by(EdgeGPUMetrics.timestamp.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def create_metric(self, payload: dict) -> EdgeGPUMetrics:
        metric = EdgeGPUMetrics(**payload)
        self.session.add(metric)
        self.session.commit()
        self.session.refresh(metric)
        return metric

    def seed_profiles(self) -> None:
        existing_models = {row[0] for row in self.session.execute(select(ConsumerGPUProfile.gpu_model)).all()}
        created = 0
        for profile in CONSUMER_GPU_PROFILES.values():
            if profile["gpu_model"] in existing_models:
                continue
            self.session.add(ConsumerGPUProfile(**profile))
            created += 1
        if created:
            self.session.commit()

    async def discover_and_register_edge_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan and register edge GPUs for a miner"""
        # Placeholder for GPU discovery logic
        return {
            "miner_id": miner_id,
            "gpus": [],
            "registered": 0,
            "edge_optimized": 0,
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
