from sqlalchemy.orm import Session
from typing import Annotated
from fastapi import Depends
from typing import List, Optional
from sqlmodel import select
from ..domain.gpu_marketplace import ConsumerGPUProfile, GPUArchitecture, EdgeGPUMetrics
from ..data.consumer_gpu_profiles import CONSUMER_GPU_PROFILES
from ..storage import get_session


class EdgeGPUService:
    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        self.session = session

    def list_profiles(
        self,
        architecture: Optional[GPUArchitecture] = None,
        edge_optimized: Optional[bool] = None,
        min_memory_gb: Optional[int] = None,
    ) -> List[ConsumerGPUProfile]:
        self.seed_profiles()
        stmt = select(ConsumerGPUProfile)
        if architecture:
            stmt = stmt.where(ConsumerGPUProfile.architecture == architecture)
        if edge_optimized is not None:
            stmt = stmt.where(ConsumerGPUProfile.edge_optimized == edge_optimized)
        if min_memory_gb is not None:
            stmt = stmt.where(ConsumerGPUProfile.memory_gb >= min_memory_gb)
        return list(self.session.execute(stmt).all())

    def list_metrics(self, gpu_id: str, limit: int = 100) -> List[EdgeGPUMetrics]:
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
        existing_models = set(self.session.execute(select(ConsumerGPUProfile.gpu_model)).all())
        created = 0
        for profile in CONSUMER_GPU_PROFILES:
            if profile["gpu_model"] in existing_models:
                continue
            self.session.add(ConsumerGPUProfile(**profile))
            created += 1
        if created:
            self.session.commit()
