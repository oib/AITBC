"""
Compute Consumer Agent - for agents that consume computational resources
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from .agent import Agent, AgentCapabilities

from aitbc import get_logger

logger = get_logger(__name__)


@dataclass
class JobRequest:
    """Compute job request specification"""

    consumer_id: str
    job_type: str
    model_id: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    requirements: Optional[Dict[str, Any]] = None
    max_price_per_hour: float = 0.0
    priority: str = "normal"
    deadline: Optional[str] = None


@dataclass
class JobResult:
    """Result from a compute job"""

    job_id: str
    provider_id: str
    status: str  # "completed", "failed", "timeout"
    output: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    cost: float = 0.0
    quality_score: Optional[float] = None


class ComputeConsumer(Agent):
    """Agent that consumes computational resources from the network"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pending_jobs: List[JobRequest] = []
        self.completed_jobs: List[JobResult] = []
        self.total_spent: float = 0.0

    async def submit_job(
        self,
        job_type: str,
        input_data: Dict[str, Any],
        requirements: Optional[Dict[str, Any]] = None,
        max_price: float = 0.0,
    ) -> str:
        """Submit a compute job to the network"""
        job = JobRequest(
            consumer_id=self.identity.id,
            job_type=job_type,
            input_data=input_data,
            requirements=requirements or {},
            max_price_per_hour=max_price,
        )
        self.pending_jobs.append(job)
        logger.info(f"Job submitted: {job_type} by {self.identity.id}")
        # TODO: Submit to coordinator for matching
        await asyncio.sleep(0.1)
        return f"job_{self.identity.id}_{len(self.pending_jobs)}"

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Check status of a submitted job"""
        # TODO: Query coordinator for job status
        return {"job_id": job_id, "status": "pending", "progress": 0.0}

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        logger.info(f"Job cancelled: {job_id}")
        return True

    def get_spending_summary(self) -> Dict[str, Any]:
        """Get spending summary"""
        return {
            "total_spent": self.total_spent,
            "completed_jobs": len(self.completed_jobs),
            "pending_jobs": len(self.pending_jobs),
        }
