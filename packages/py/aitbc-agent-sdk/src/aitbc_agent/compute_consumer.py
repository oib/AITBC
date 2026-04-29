"""
Compute Consumer Agent - for agents that consume computational resources
"""

import asyncio
import httpx
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from .agent import Agent, AgentCapabilities

from aitbc.aitbc_logging import get_logger

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

    def __init__(
        self,
        identity: AgentIdentity,
        capabilities: AgentCapabilities,
        coordinator_url: Optional[str] = None,
    ) -> None:
        super().__init__(identity, capabilities, coordinator_url)
        self.pending_jobs: List[JobRequest] = []
        self.completed_jobs: List[JobResult] = []
        self.total_spent: float = 0.0

    @classmethod
    def create(cls, name: str, agent_type: str, capabilities: Dict[str, Any]) -> "ComputeConsumer":
        """Create a new ComputeConsumer agent"""
        from .agent import AgentCapabilities, AgentIdentity

        # Generate cryptographic keys
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        # Create identity
        identity = AgentIdentity(
            id=str(uuid.uuid4()),
            name=name,
            address=f"0x{uuid.uuid4().hex[:40]}",
            public_key=public_key_pem,
            private_key=private_key_pem,
        )

        # Create capabilities
        agent_capabilities = AgentCapabilities(
            compute_type=capabilities.get("compute_type", "general"),
            gpu_memory=capabilities.get("gpu_memory"),
            supported_models=capabilities.get("supported_models"),
            performance_score=capabilities.get("performance_score", 0.0),
            max_concurrent_jobs=capabilities.get("max_concurrent_jobs", 1),
            specialization=capabilities.get("specialization"),
        )

        return cls(identity, agent_capabilities)

    async def submit_job(
        self,
        job_type: str,
        input_data: Dict[str, Any],
        requirements: Optional[Dict[str, Any]] = None,
        max_price: float = 0.0,
    ) -> str:
        """Submit a compute job to the network via coordinator API"""
        job = JobRequest(
            consumer_id=self.identity.id,
            job_type=job_type,
            input_data=input_data,
            requirements=requirements or {},
            max_price_per_hour=max_price,
        )
        self.pending_jobs.append(job)
        logger.info(f"Job submitted: {job_type} by {self.identity.id}")
        
        # Submit to coordinator for matching
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.coordinator_url}/v1/jobs",
                    json={
                        "consumer_id": job.consumer_id,
                        "job_type": job.job_type,
                        "input_data": job.input_data,
                        "requirements": job.requirements,
                        "max_price_per_hour": job.max_price_per_hour,
                        "priority": job.priority
                    },
                    timeout=10
                )
                if response.status_code == 201:
                    result = response.json()
                    return result.get("job_id", f"job_{self.identity.id}_{len(self.pending_jobs)}")
                else:
                    logger.error(f"Failed to submit job to coordinator: {response.status_code}")
                    return f"job_{self.identity.id}_{len(self.pending_jobs)}"
        except Exception as e:
            logger.error(f"Error submitting job to coordinator: {e}")
            return f"job_{self.identity.id}_{len(self.pending_jobs)}"

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Query coordinator for job status"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.coordinator_url}/v1/jobs/{job_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"job_id": job_id, "status": "error", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Error querying job status: {e}")
            return {"job_id": job_id, "status": "error", "error": str(e)}

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

    async def __aenter__(self) -> "ComputeConsumer":
        """Async context manager entry - register consumer"""
        await self.register() if hasattr(self, 'register') else None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup consumer resources"""
        # Cancel any pending jobs
        for job in self.pending_jobs[:]:
            await self.cancel_job(job.job_id if hasattr(job, 'job_id') else str(job))
        
        if exc_type is not None:
            logger.error(f"Consumer {self.identity.id} exiting with exception: {exc_val}")
        else:
            logger.info(f"Consumer {self.identity.id} exiting normally. Total spent: {self.total_spent} AITBC")
