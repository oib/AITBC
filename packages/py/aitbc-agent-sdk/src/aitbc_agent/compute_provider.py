"""
Compute Provider Agent - for agents that provide computational resources
"""

import asyncio
import httpx
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC, timedelta
from dataclasses import dataclass, asdict
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from .agent import Agent, AgentCapabilities, AgentIdentity

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.http_client import AITBCHTTPClient

logger = get_logger(__name__)


@dataclass
class ResourceOffer:
    """Resource offering specification"""

    provider_id: str
    compute_type: str
    gpu_memory: int
    supported_models: List[str]
    price_per_hour: float
    availability_schedule: Dict[str, Any]
    max_concurrent_jobs: int
    quality_guarantee: float = 0.95


@dataclass
class JobExecution:
    """Job execution tracking"""

    job_id: str
    consumer_id: str
    start_time: datetime
    expected_duration: timedelta
    actual_duration: Optional[timedelta] = None
    status: str = "running"  # running, completed, failed
    quality_score: Optional[float] = None


class ComputeProvider(Agent):
    """Agent that provides computational resources"""

    def __init__(
        self,
        identity: AgentIdentity,
        capabilities: AgentCapabilities,
        coordinator_url: Optional[str] = None,
    ) -> None:
        super().__init__(identity, capabilities, coordinator_url)
        self.current_offers: List[ResourceOffer] = []
        self.active_jobs: List[JobExecution] = []
        self.earnings: float = 0.0
        self.utilization_rate: float = 0.0
        self.pricing_model: Dict[str, Any] = {}
        self.dynamic_pricing: Dict[str, Any] = {}

    @classmethod
    def create_provider(
        cls, name: str, capabilities: Dict[str, Any], pricing_model: Dict[str, Any]
    ) -> "ComputeProvider":
        """Create and register a compute provider"""
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

        provider = cls(identity, agent_capabilities)
        provider.pricing_model = pricing_model
        return provider

    async def offer_resources(
        self,
        price_per_hour: float,
        availability_schedule: Dict[str, Any],
        max_concurrent_jobs: int = 3,
    ) -> bool:
        """Offer computational resources on the marketplace"""
        try:
            offer = ResourceOffer(
                provider_id=self.identity.id,
                compute_type=self.capabilities.compute_type,
                gpu_memory=self.capabilities.gpu_memory or 0,
                supported_models=self.capabilities.supported_models or [],
                price_per_hour=price_per_hour,
                availability_schedule=availability_schedule,
                max_concurrent_jobs=max_concurrent_jobs,
            )

            # Submit to marketplace
            await self._submit_to_marketplace(offer)
            self.current_offers.append(offer)

            logger.info(f"Resource offer submitted: {price_per_hour} AITBC/hour")
            return True

        except Exception as e:
            logger.error(f"Failed to offer resources: {e}")
            return False

    async def set_availability(self, schedule: Dict[str, Any]) -> bool:
        """Set availability schedule for resource offerings"""
        try:
            # Update all current offers with new schedule
            for offer in self.current_offers:
                offer.availability_schedule = schedule
                await self._update_marketplace_offer(offer)

            logger.info("Availability schedule updated")
            return True

        except Exception as e:
            logger.error(f"Failed to update availability: {e}")
            return False

    async def enable_dynamic_pricing(
        self,
        base_rate: float,
        demand_threshold: float = 0.8,
        max_multiplier: float = 2.0,
        adjustment_frequency: str = "15min",
    ) -> bool:
        """Enable dynamic pricing based on market demand"""
        try:
            self.dynamic_pricing = {
                "base_rate": base_rate,
                "demand_threshold": demand_threshold,
                "max_multiplier": max_multiplier,
                "adjustment_frequency": adjustment_frequency,
                "enabled": True,
            }

            # Start dynamic pricing task
            asyncio.create_task(self._dynamic_pricing_loop())

            logger.info("Dynamic pricing enabled")
            return True

        except Exception as e:
            logger.error(f"Failed to enable dynamic pricing: {e}")
            return False

    async def _dynamic_pricing_loop(self) -> None:
        """Background task for dynamic price adjustments"""
        while getattr(self, "dynamic_pricing", {}).get("enabled", False):
            try:
                # Get current utilization
                current_utilization = (
                    len(self.active_jobs) / self.capabilities.max_concurrent_jobs
                )

                # Adjust pricing based on demand
                if current_utilization > self.dynamic_pricing["demand_threshold"]:
                    # High demand - increase price
                    multiplier = min(
                        1.0
                        + (
                            current_utilization
                            - self.dynamic_pricing["demand_threshold"]
                        )
                        * 2,
                        self.dynamic_pricing["max_multiplier"],
                    )
                else:
                    # Low demand - decrease price
                    multiplier = max(
                        0.5,
                        current_utilization / self.dynamic_pricing["demand_threshold"],
                    )

                new_price = self.dynamic_pricing["base_rate"] * multiplier

                # Update marketplace offers
                for offer in self.current_offers:
                    offer.price_per_hour = new_price
                    await self._update_marketplace_offer(offer)

                logger.debug(
                    f"Dynamic pricing: utilization={current_utilization:.2f}, price={new_price:.3f} AITBC/h"
                )

            except Exception as e:
                logger.error(f"Dynamic pricing error: {e}")

            # Wait for next adjustment
            await asyncio.sleep(900)  # 15 minutes

    async def accept_job(self, job_request: Dict[str, Any]) -> bool:
        """Accept and execute a computational job"""
        try:
            # Check capacity
            if len(self.active_jobs) >= self.capabilities.max_concurrent_jobs:
                return False

            # Create job execution record
            job = JobExecution(
                job_id=job_request["job_id"],
                consumer_id=job_request["consumer_id"],
                start_time=datetime.now(datetime.UTC),
                expected_duration=timedelta(hours=job_request["estimated_hours"]),
            )

            self.active_jobs.append(job)
            self._update_utilization()

            # Execute job (simulate)
            asyncio.create_task(self._execute_job(job, job_request))

            logger.info(f"Job accepted: {job.job_id} from {job.consumer_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to accept job: {e}")
            return False

    async def _execute_job(
        self, job: JobExecution, job_request: Dict[str, Any]
    ) -> None:
        """Execute a computational job"""
        try:
            # Simulate job execution
            execution_time = timedelta(hours=job_request["estimated_hours"])
            await asyncio.sleep(5)  # Simulate processing time

            # Update job completion
            job.actual_duration = execution_time
            job.status = "completed"
            job.quality_score = 0.95  # Simulate quality score

            # Calculate earnings
            earnings = job_request["estimated_hours"] * job_request["agreed_price"]
            self.earnings += earnings

            # Remove from active jobs
            self.active_jobs.remove(job)
            self._update_utilization()

            # Notify consumer
            await self._notify_job_completion(job, earnings)

            logger.info(f"Job completed: {job.job_id}, earned {earnings} AITBC")

        except Exception as e:
            job.status = "failed"
            logger.error(f"Job execution failed: {job.job_id} - {e}")

    async def _notify_job_completion(self, job: JobExecution, earnings: float) -> None:
        """Notify consumer about job completion"""
        notification = {
            "job_id": job.job_id,
            "status": job.status,
            "completion_time": datetime.now(datetime.UTC).isoformat(),
            "duration_hours": (
                job.actual_duration.total_seconds() / 3600
                if job.actual_duration
                else None
            ),
            "quality_score": job.quality_score,
            "cost": earnings,
        }

        await self.send_message(job.consumer_id, "job_completion", notification)

    def _update_utilization(self) -> None:
        """Update current utilization rate"""
        self.utilization_rate = (
            len(self.active_jobs) / self.capabilities.max_concurrent_jobs
        )

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get provider performance metrics"""
        completed_jobs = [j for j in self.active_jobs if j.status == "completed"]

        return {
            "utilization_rate": self.utilization_rate,
            "active_jobs": len(self.active_jobs),
            "total_earnings": self.earnings,
            "average_job_duration": (
                sum(
                    j.actual_duration.total_seconds()
                    for j in completed_jobs
                    if j.actual_duration
                )
                / len(completed_jobs)
                if completed_jobs
                else 0
            ),
            "quality_score": (
                sum(
                    j.quality_score
                    for j in completed_jobs
                    if j.quality_score is not None
                )
                / len(completed_jobs)
                if completed_jobs
                else 0
            ),
            "current_offers": len(self.current_offers),
        }

    async def _submit_to_marketplace(self, offer: ResourceOffer) -> str:
        """Submit resource offer to marketplace"""
        try:
            offer_data = {
                "provider_id": offer.provider_id,
                "compute_type": offer.compute_type,
                "gpu_memory": offer.gpu_memory,
                "supported_models": offer.supported_models,
                "price_per_hour": offer.price_per_hour,
                "availability_schedule": offer.availability_schedule,
                "max_concurrent_jobs": offer.max_concurrent_jobs,
                "quality_guarantee": offer.quality_guarantee,
            }
            
            response = await self.http_client.post(
                "/v1/marketplace/offers",
                json=offer_data
            )
            
            if response.status_code == 201:
                result = response.json()
                offer_id = result.get("offer_id")
                logger.info(f"Offer submitted successfully: {offer_id}")
                return offer_id
            else:
                logger.error(f"Failed to submit offer: {response.status_code}")
                raise NetworkError(f"Marketplace submission failed: {response.status_code}")
        except NetworkError:
            raise
        except Exception as e:
            logger.error(f"Error submitting to marketplace: {e}")
            raise

    async def _update_marketplace_offer(self, offer: ResourceOffer) -> None:
        """Update existing marketplace offer"""
        try:
            offer_data = {
                "provider_id": offer.provider_id,
                "compute_type": offer.compute_type,
                "gpu_memory": offer.gpu_memory,
                "supported_models": offer.supported_models,
                "price_per_hour": offer.price_per_hour,
                "availability_schedule": offer.availability_schedule,
                "max_concurrent_jobs": offer.max_concurrent_jobs,
                "quality_guarantee": offer.quality_guarantee,
            }
            
            response = await self.http_client.put(
                f"/v1/marketplace/offers/{offer.provider_id}",
                json=offer_data
            )
            
            if response.status_code == 200:
                logger.info(f"Offer updated successfully: {offer.provider_id}")
            else:
                logger.error(f"Failed to update offer: {response.status_code}")
                raise NetworkError(f"Marketplace update failed: {response.status_code}")
        except NetworkError:
            raise
        except Exception as e:
            logger.error(f"Error updating marketplace offer: {e}")
            raise

    @classmethod
    def assess_capabilities(cls) -> Dict[str, Any]:
        """Assess available computational capabilities"""
        import subprocess
        import re
        
        capabilities = {
            "gpu_memory": 0,
            "supported_models": [],
            "performance_score": 0.0,
            "max_concurrent_jobs": 1,
            "gpu_count": 0,
            "compute_capability": "unknown",
        }
        
        try:
            # Try to detect GPU using nvidia-smi
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,name,compute_cap", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                gpu_lines = result.stdout.strip().split("\n")
                capabilities["gpu_count"] = len(gpu_lines)
                
                total_memory = 0
                for line in gpu_lines:
                    parts = line.split(", ")
                    if len(parts) >= 3:
                        # Parse memory (e.g., "8192 MiB")
                        memory_str = parts[0].strip()
                        memory_match = re.search(r'(\d+)', memory_str)
                        if memory_match:
                            total_memory += int(memory_match.group(1))
                        
                        # Get compute capability
                        capabilities["compute_capability"] = parts[2].strip()
                
                capabilities["gpu_memory"] = total_memory
                capabilities["max_concurrent_jobs"] = min(len(gpu_lines), 4)
                
                # Estimate performance score based on GPU memory and compute capability
                if total_memory >= 24000:
                    capabilities["performance_score"] = 0.95
                elif total_memory >= 16000:
                    capabilities["performance_score"] = 0.85
                elif total_memory >= 8000:
                    capabilities["performance_score"] = 0.75
                else:
                    capabilities["performance_score"] = 0.65
                
                # Determine supported models based on GPU memory
                if total_memory >= 24000:
                    capabilities["supported_models"] = ["llama3.2", "mistral", "deepseek", "gpt-j", "bloom"]
                elif total_memory >= 16000:
                    capabilities["supported_models"] = ["llama3.2", "mistral", "deepseek"]
                elif total_memory >= 8000:
                    capabilities["supported_models"] = ["llama3.2", "mistral"]
                else:
                    capabilities["supported_models"] = ["llama3.2"]
                
                logger.info(f"GPU capabilities detected: {capabilities}")
            else:
                logger.warning("nvidia-smi not available, using CPU-only capabilities")
                capabilities["supported_models"] = ["llama3.2-quantized"]
                capabilities["performance_score"] = 0.3
                capabilities["max_concurrent_jobs"] = 1
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"GPU detection failed: {e}, using CPU-only capabilities")
            capabilities["supported_models"] = ["llama3.2-quantized"]
            capabilities["performance_score"] = 0.3
            capabilities["max_concurrent_jobs"] = 1
        except Exception as e:
            logger.error(f"Error assessing capabilities: {e}")
            capabilities["supported_models"] = ["llama3.2-quantized"]
            capabilities["performance_score"] = 0.3
            capabilities["max_concurrent_jobs"] = 1
        
        return capabilities

    async def __aenter__(self) -> "ComputeProvider":
        """Async context manager entry - register provider and start services"""
        await super().__aenter__() if hasattr(super(), '__aenter__') else self.register()
        # Start dynamic pricing if enabled
        if self.dynamic_pricing.get("enabled", False):
            asyncio.create_task(self._dynamic_pricing_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup provider resources"""
        # Stop dynamic pricing
        if hasattr(self, 'dynamic_pricing'):
            self.dynamic_pricing["enabled"] = False
        
        # Complete any remaining jobs
        for job in self.active_jobs[:]:
            if job.status == "running":
                job.status = "failed"
                logger.warning(f"Job {job.job_id} marked as failed due to provider shutdown")
        
        # Call parent cleanup
        if hasattr(super(), '__aexit__'):
            await super().__aexit__(exc_type, exc_val, exc_tb)
        
        if exc_type is not None:
            logger.error(f"Provider {self.identity.id} exiting with exception: {exc_val}")
        else:
            logger.info(f"Provider {self.identity.id} exiting normally. Total earnings: {self.earnings} AITBC")
