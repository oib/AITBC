"""
Compute Provider Agent - for agents that provide computational resources
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from .agent import Agent, AgentCapabilities

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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_offers: List[ResourceOffer] = []
        self.active_jobs: List[JobExecution] = []
        self.earnings = 0.0
        self.utilization_rate = 0.0
        
    @classmethod
    def register(cls, name: str, capabilities: Dict[str, Any], pricing_model: Dict[str, Any]) -> 'ComputeProvider':
        """Register as a compute provider"""
        agent = super().create(name, "compute_provider", capabilities)
        provider = cls(agent.identity, agent.capabilities)
        provider.pricing_model = pricing_model
        return provider
    
    async def offer_resources(self, price_per_hour: float, availability_schedule: Dict[str, Any], max_concurrent_jobs: int = 3) -> bool:
        """Offer computational resources on the marketplace"""
        try:
            offer = ResourceOffer(
                provider_id=self.identity.id,
                compute_type=self.capabilities.compute_type,
                gpu_memory=self.capabilities.gpu_memory or 0,
                supported_models=self.capabilities.supported_models,
                price_per_hour=price_per_hour,
                availability_schedule=availability_schedule,
                max_concurrent_jobs=max_concurrent_jobs
            )
            
            # Submit to marketplace
            await self._submit_to_marketplace(offer)
            self.current_offers.append(offer)
            
            print(f"Resource offer submitted: {price_per_hour} AITBC/hour")
            return True
            
        except Exception as e:
            print(f"Failed to offer resources: {e}")
            return False
    
    async def set_availability(self, schedule: Dict[str, Any]) -> bool:
        """Set availability schedule for resource offerings"""
        try:
            # Update all current offers with new schedule
            for offer in self.current_offers:
                offer.availability_schedule = schedule
                await self._update_marketplace_offer(offer)
            
            print("Availability schedule updated")
            return True
            
        except Exception as e:
            print(f"Failed to update availability: {e}")
            return False
    
    async def enable_dynamic_pricing(self, base_rate: float, demand_threshold: float = 0.8, max_multiplier: float = 2.0, adjustment_frequency: str = "15min") -> bool:
        """Enable dynamic pricing based on market demand"""
        try:
            self.dynamic_pricing = {
                "base_rate": base_rate,
                "demand_threshold": demand_threshold,
                "max_multiplier": max_multiplier,
                "adjustment_frequency": adjustment_frequency,
                "enabled": True
            }
            
            # Start dynamic pricing task
            asyncio.create_task(self._dynamic_pricing_loop())
            
            print("Dynamic pricing enabled")
            return True
            
        except Exception as e:
            print(f"Failed to enable dynamic pricing: {e}")
            return False
    
    async def _dynamic_pricing_loop(self):
        """Background task for dynamic price adjustments"""
        while getattr(self, 'dynamic_pricing', {}).get('enabled', False):
            try:
                # Get current utilization
                current_utilization = len(self.active_jobs) / self.capabilities.max_concurrent_jobs
                
                # Adjust pricing based on demand
                if current_utilization > self.dynamic_pricing['demand_threshold']:
                    # High demand - increase price
                    multiplier = min(
                        1.0 + (current_utilization - self.dynamic_pricing['demand_threshold']) * 2,
                        self.dynamic_pricing['max_multiplier']
                    )
                else:
                    # Low demand - decrease price
                    multiplier = max(0.5, current_utilization / self.dynamic_pricing['demand_threshold'])
                
                new_price = self.dynamic_pricing['base_rate'] * multiplier
                
                # Update marketplace offers
                for offer in self.current_offers:
                    offer.price_per_hour = new_price
                    await self._update_marketplace_offer(offer)
                
                print(f"Dynamic pricing: utilization={current_utilization:.2f}, price={new_price:.3f} AITBC/h")
                
            except Exception as e:
                print(f"Dynamic pricing error: {e}")
            
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
                start_time=datetime.utcnow(),
                expected_duration=timedelta(hours=job_request["estimated_hours"])
            )
            
            self.active_jobs.append(job)
            self._update_utilization()
            
            # Execute job (simulate)
            asyncio.create_task(self._execute_job(job, job_request))
            
            print(f"Job accepted: {job.job_id} from {job.consumer_id}")
            return True
            
        except Exception as e:
            print(f"Failed to accept job: {e}")
            return False
    
    async def _execute_job(self, job: JobExecution, job_request: Dict[str, Any]):
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
            
            print(f"Job completed: {job.job_id}, earned {earnings} AITBC")
            
        except Exception as e:
            job.status = "failed"
            print(f"Job execution failed: {job.job_id} - {e}")
    
    async def _notify_job_completion(self, job: JobExecution, earnings: float):
        """Notify consumer about job completion"""
        notification = {
            "job_id": job.job_id,
            "status": job.status,
            "completion_time": datetime.utcnow().isoformat(),
            "duration_hours": job.actual_duration.total_seconds() / 3600 if job.actual_duration else None,
            "quality_score": job.quality_score,
            "cost": earnings
        }
        
        await self.send_message(job.consumer_id, "job_completion", notification)
    
    def _update_utilization(self):
        """Update current utilization rate"""
        self.utilization_rate = len(self.active_jobs) / self.capabilities.max_concurrent_jobs
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get provider performance metrics"""
        completed_jobs = [j for j in self.active_jobs if j.status == "completed"]
        
        return {
            "utilization_rate": self.utilization_rate,
            "active_jobs": len(self.active_jobs),
            "total_earnings": self.earnings,
            "average_job_duration": sum(j.actual_duration.total_seconds() for j in completed_jobs) / len(completed_jobs) if completed_jobs else 0,
            "quality_score": sum(j.quality_score for j in completed_jobs if j.quality_score) / len(completed_jobs) if completed_jobs else 0,
            "current_offers": len(self.current_offers)
        }
    
    async def _submit_to_marketplace(self, offer: ResourceOffer):
        """Submit resource offer to marketplace (placeholder)"""
        # TODO: Implement actual marketplace submission
        await asyncio.sleep(0.1)
    
    async def _update_marketplace_offer(self, offer: ResourceOffer):
        """Update existing marketplace offer (placeholder)"""
        # TODO: Implement actual marketplace update
        await asyncio.sleep(0.1)
    
    @classmethod
    def assess_capabilities(cls) -> Dict[str, Any]:
        """Assess available computational capabilities"""
        # TODO: Implement actual capability assessment
        return {
            "gpu_memory": 24,
            "supported_models": ["llama3.2", "mistral", "deepseek"],
            "performance_score": 0.95,
            "max_concurrent_jobs": 3
        }
