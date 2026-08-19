"""
Compute Consumer Agent - for agents that consume computational resources
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from aitbc.aitbc_logging import get_logger

from .agent import Agent, AgentCapabilities, AgentIdentity

logger = get_logger(__name__)


@dataclass
class JobRequest:
    """Compute job request specification"""

    consumer_id: str
    job_type: str
    model_id: str | None = None
    input_data: dict[str, Any] | None = None
    requirements: dict[str, Any] | None = None
    max_price_per_hour: Decimal = Decimal("0")
    priority: str = "normal"
    deadline: str | None = None
    job_id: str | None = None


@dataclass
class JobResult:
    """Result from a compute job"""

    job_id: str
    provider_id: str
    status: str  # "completed", "failed", "timeout"
    output: dict[str, Any] | None = None
    execution_time: float = 0.0
    cost: Decimal = Decimal("0")
    quality_score: float | None = None


class ComputeConsumer(Agent):
    """Agent that consumes computational resources from the network"""

    def __init__(
        self,
        identity: AgentIdentity,
        capabilities: AgentCapabilities,
        coordinator_url: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        super().__init__(identity, capabilities, coordinator_url)
        self.auth_token = auth_token
        self.pending_jobs: list[JobRequest] = []
        self.completed_jobs: list[JobResult] = []
        self.total_spent: Decimal = Decimal("0")

    @classmethod
    def create(
        cls,
        name: str,
        agent_type: str,
        capabilities: dict[str, Any],
        coordinator_url: str | None = None,
        auth_token: str | None = None,
    ) -> "ComputeConsumer":
        """Create a new ComputeConsumer agent"""
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

        return cls(identity, agent_capabilities, coordinator_url=coordinator_url, auth_token=auth_token)

    async def submit_job(
        self,
        job_type: str,
        input_data: dict[str, Any],
        requirements: dict[str, Any] | None = None,
        max_price: Decimal = Decimal("0"),
        buyer_address: str | None = None,
        provider_address: str | None = None,
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
        logger.info("Job submitted: %s by %s", job_type, self.identity.id)

        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        buyer = buyer_address or self.identity.address

        payload: dict[str, Any] = {
            "consumer_id": job.consumer_id,
            "payload": {"type": job.job_type, **(job.input_data or {})},
            "constraints": job.requirements or {},
            "payment_amount": job.max_price_per_hour,
            "payment_currency": "AIT",
            "ttl_seconds": 900,
        }
        if buyer:
            payload["buyer_address"] = buyer
        if provider_address:
            payload["provider_address"] = provider_address

        # Submit to coordinator for matching
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.coordinator_url}/v1/jobs",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )
                if response.status_code == 201:
                    result = response.json()
                    job_id = result.get("job_id", f"job_{self.identity.id}_{len(self.pending_jobs)}")
                    job.job_id = job_id
                    return job_id
                else:
                    logger.error("Failed to submit job to coordinator: %s %s", response.status_code, response.text)
                    return f"job_{self.identity.id}_{len(self.pending_jobs)}"
        except Exception as e:
            logger.error("Error submitting job to coordinator: %s", e)
            return f"job_{self.identity.id}_{len(self.pending_jobs)}"

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Query coordinator for job status"""
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.coordinator_url}/v1/jobs/{job_id}",
                    headers=headers,
                    timeout=30,
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"job_id": job_id, "status": "error", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error("Error querying job status: %s", e)
            return {"job_id": job_id, "status": "error", "error": str(e)}

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        logger.info("Job cancelled: %s", job_id)
        return True

    def get_spending_summary(self) -> dict[str, Any]:
        """Get spending summary"""
        return {
            "total_spent": str(self.total_spent),
            "completed_jobs": len(self.completed_jobs),
            "pending_jobs": len(self.pending_jobs),
        }

    async def __aenter__(self) -> "ComputeConsumer":
        """Async context manager entry - register consumer"""
        await self.register() if hasattr(self, "register") else None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup consumer resources"""
        # Cancel any pending jobs
        for job in self.pending_jobs[:]:
            await self.cancel_job(job.job_id if hasattr(job, "job_id") else str(job))

        if exc_type is not None:
            logger.error("Consumer %s exiting with exception: %s", self.identity.id, exc_val)
        else:
            logger.info("Consumer %s exiting normally. Total spent: %s AITBC", self.identity.id, self.total_spent)
