"""Miner Registry Implementation"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import asyncio


@dataclass
class MinerInfo:
    """Miner information"""

    miner_id: str
    pool_id: str
    capabilities: List[str]
    gpu_info: Dict[str, Any]
    endpoint: Optional[str]
    max_concurrent_jobs: int
    status: str = "available"
    current_jobs: int = 0
    score: float = 100.0
    jobs_completed: int = 0
    jobs_failed: int = 0
    uptime_percent: float = 100.0
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    gpu_utilization: float = 0.0
    memory_used_gb: float = 0.0


@dataclass
class PoolInfo:
    """Pool information"""

    pool_id: str
    name: str
    description: Optional[str]
    operator: str
    fee_percent: float
    min_payout: float
    payout_schedule: str
    miner_count: int = 0
    total_hashrate: float = 0.0
    jobs_completed_24h: int = 0
    earnings_24h: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobAssignment:
    """Job assignment record"""

    job_id: str
    miner_id: str
    pool_id: str
    model: str
    status: str = "assigned"
    assigned_at: datetime = field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class MinerRegistry:
    """Registry for managing miners and pools"""

    def __init__(self):
        self._miners: Dict[str, MinerInfo] = {}
        self._pools: Dict[str, PoolInfo] = {}
        self._jobs: Dict[str, JobAssignment] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        miner_id: str,
        pool_id: str,
        capabilities: List[str],
        gpu_info: Dict[str, Any],
        endpoint: Optional[str] = None,
        max_concurrent_jobs: int = 1,
    ) -> MinerInfo:
        """Register a new miner."""
        async with self._lock:
            if miner_id in self._miners:
                raise ValueError(f"Miner {miner_id} already registered")

            if pool_id not in self._pools:
                raise ValueError(f"Pool {pool_id} not found")

            miner = MinerInfo(
                miner_id=miner_id,
                pool_id=pool_id,
                capabilities=capabilities,
                gpu_info=gpu_info,
                endpoint=endpoint,
                max_concurrent_jobs=max_concurrent_jobs,
            )

            self._miners[miner_id] = miner
            self._pools[pool_id].miner_count += 1

            return miner

    async def get(self, miner_id: str) -> Optional[MinerInfo]:
        """Get miner by ID."""
        return self._miners.get(miner_id)

    async def list(
        self,
        pool_id: Optional[str] = None,
        status: Optional[str] = None,
        capability: Optional[str] = None,
        exclude_miner: Optional[str] = None,
        limit: int = 50,
    ) -> List[MinerInfo]:
        """List miners with filters."""
        miners = list(self._miners.values())

        if pool_id:
            miners = [m for m in miners if m.pool_id == pool_id]
        if status:
            miners = [m for m in miners if m.status == status]
        if capability:
            miners = [m for m in miners if capability in m.capabilities]
        if exclude_miner:
            miners = [m for m in miners if m.miner_id != exclude_miner]

        return miners[:limit]

    async def update_status(
        self,
        miner_id: str,
        status: str,
        current_jobs: int = 0,
        gpu_utilization: float = 0.0,
        memory_used_gb: float = 0.0,
    ):
        """Update miner status."""
        async with self._lock:
            if miner_id in self._miners:
                miner = self._miners[miner_id]
                miner.status = status
                miner.current_jobs = current_jobs
                miner.gpu_utilization = gpu_utilization
                miner.memory_used_gb = memory_used_gb
                miner.last_heartbeat = datetime.utcnow()

    async def update_capabilities(self, miner_id: str, capabilities: List[str]):
        """Update miner capabilities."""
        async with self._lock:
            if miner_id in self._miners:
                self._miners[miner_id].capabilities = capabilities

    async def unregister(self, miner_id: str):
        """Unregister a miner."""
        async with self._lock:
            if miner_id in self._miners:
                pool_id = self._miners[miner_id].pool_id
                del self._miners[miner_id]
                if pool_id in self._pools:
                    self._pools[pool_id].miner_count -= 1

    # Pool management
    async def create_pool(
        self,
        pool_id: str,
        name: str,
        operator: str,
        description: Optional[str] = None,
        fee_percent: float = 1.0,
        min_payout: float = 10.0,
        payout_schedule: str = "daily",
    ) -> PoolInfo:
        """Create a new pool."""
        async with self._lock:
            if pool_id in self._pools:
                raise ValueError(f"Pool {pool_id} already exists")

            pool = PoolInfo(
                pool_id=pool_id,
                name=name,
                description=description,
                operator=operator,
                fee_percent=fee_percent,
                min_payout=min_payout,
                payout_schedule=payout_schedule,
            )

            self._pools[pool_id] = pool
            return pool

    async def get_pool(self, pool_id: str) -> Optional[PoolInfo]:
        """Get pool by ID."""
        return self._pools.get(pool_id)

    async def list_pools(self, limit: int = 50, offset: int = 0) -> List[PoolInfo]:
        """List all pools."""
        pools = list(self._pools.values())
        return pools[offset : offset + limit]

    async def get_pool_stats(self, pool_id: str) -> Dict[str, Any]:
        """Get pool statistics."""
        pool = self._pools.get(pool_id)
        if not pool:
            return {}

        miners = await self.list(pool_id=pool_id)
        active = [m for m in miners if m.status == "available"]

        return {
            "pool_id": pool_id,
            "miner_count": len(miners),
            "active_miners": len(active),
            "total_jobs": sum(m.jobs_completed for m in miners),
            "jobs_24h": pool.jobs_completed_24h,
            "total_earnings": pool.earnings_24h * 30,  # Estimate: 24h * 30 = monthly
            "earnings_24h": pool.earnings_24h,
            "avg_response_time_ms": sum(m.jobs_completed * 500 for m in miners)
            / max(
                sum(m.jobs_completed for m in miners), 1
            ),  # Estimate: 500ms avg per job
            "uptime_percent": sum(m.uptime_percent for m in miners)
            / max(len(miners), 1),
        }

    async def update_pool(self, pool_id: str, updates: Dict[str, Any]):
        """Update pool settings."""
        async with self._lock:
            if pool_id in self._pools:
                pool = self._pools[pool_id]
                for key, value in updates.items():
                    if hasattr(pool, key):
                        setattr(pool, key, value)

    async def delete_pool(self, pool_id: str):
        """Delete a pool."""
        async with self._lock:
            if pool_id in self._pools:
                del self._pools[pool_id]

    # Job management
    async def assign_job(
        self, job_id: str, miner_id: str, deadline: Optional[datetime] = None
    ) -> JobAssignment:
        """Assign a job to a miner."""
        async with self._lock:
            miner = self._miners.get(miner_id)
            if not miner:
                raise ValueError(f"Miner {miner_id} not found")

            assignment = JobAssignment(
                job_id=job_id,
                miner_id=miner_id,
                pool_id=miner.pool_id,
                model="",  # Set by caller
                deadline=deadline,
            )

            self._jobs[job_id] = assignment
            miner.current_jobs += 1

            if miner.current_jobs >= miner.max_concurrent_jobs:
                miner.status = "busy"

            return assignment

    async def complete_job(
        self, job_id: str, miner_id: str, status: str, metrics: Dict[str, Any] = None
    ):
        """Mark a job as complete."""
        async with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.status = status
                job.completed_at = datetime.utcnow()

            if miner_id in self._miners:
                miner = self._miners[miner_id]
                miner.current_jobs = max(0, miner.current_jobs - 1)

                if status == "completed":
                    miner.jobs_completed += 1
                else:
                    miner.jobs_failed += 1

                if miner.current_jobs < miner.max_concurrent_jobs:
                    miner.status = "available"

    async def get_job(self, job_id: str) -> Optional[JobAssignment]:
        """Get job assignment."""
        return self._jobs.get(job_id)

    async def get_pending_jobs(
        self, pool_id: Optional[str] = None, limit: int = 50
    ) -> List[JobAssignment]:
        """Get pending jobs."""
        jobs = [j for j in self._jobs.values() if j.status == "assigned"]
        if pool_id:
            jobs = [j for j in jobs if j.pool_id == pool_id]
        return jobs[:limit]

    async def reassign_job(self, job_id: str, new_miner_id: str):
        """Reassign a job to a new miner."""
        async with self._lock:
            if job_id not in self._jobs:
                raise ValueError(f"Job {job_id} not found")

            job = self._jobs[job_id]
            old_miner_id = job.miner_id

            # Update old miner
            if old_miner_id in self._miners:
                self._miners[old_miner_id].current_jobs -= 1

            # Update job
            job.miner_id = new_miner_id
            job.status = "assigned"
            job.assigned_at = datetime.utcnow()

            # Update new miner
            if new_miner_id in self._miners:
                miner = self._miners[new_miner_id]
                miner.current_jobs += 1
                job.pool_id = miner.pool_id
