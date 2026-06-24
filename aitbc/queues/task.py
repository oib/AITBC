"""
Task Management Module
Provides job definitions and task queue implementation
"""

import asyncio
import heapq
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class JobStatus(Enum):
    """Job status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority levels"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(order=True)
class Job:
    """Background job"""

    priority: int
    func: Callable | None = field(default=None, compare=False)
    job_id: str | None = field(default=None, compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    status: JobStatus = field(default=JobStatus.PENDING, compare=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC), compare=False)
    started_at: datetime | None = field(default=None, compare=False)
    completed_at: datetime | None = field(default=None, compare=False)
    result: Any = field(default=None, compare=False)
    error: str | None = field(default=None, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=3, compare=False)

    def __post_init__(self):
        if self.job_id is None:
            self.job_id = str(uuid.uuid4())
        if self.func is None:
            raise ValueError("func is required")


class TaskQueue:
    """Priority-based task queue"""

    def __init__(self):
        """Initialize task queue"""
        self.queue: list[Job] = []
        self.jobs: dict[str, Job] = {}
        self.lock = asyncio.Lock()

    async def enqueue(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        priority: JobPriority = JobPriority.MEDIUM,
        max_retries: int = 3,
    ) -> str:
        """Enqueue a task"""
        if kwargs is None:
            kwargs = {}
        job = Job(priority=priority.value, func=func, args=args, kwargs=kwargs, max_retries=max_retries)
        assert job.job_id is not None  # set by __post_init__
        async with self.lock:
            heapq.heappush(self.queue, job)
            self.jobs[job.job_id] = job
        return job.job_id

    async def dequeue(self) -> Job | None:
        """Dequeue a task"""
        async with self.lock:
            if not self.queue:
                return None
            job = heapq.heappop(self.queue)
            return job

    async def get_job(self, job_id: str) -> Job | None:
        """Get job by ID"""
        return self.jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        async with self.lock:
            job = self.jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                self.queue = [j for j in self.queue if j.job_id != job_id]
                heapq.heapify(self.queue)
                return True
        return False

    async def get_queue_size(self) -> int:
        """Get queue size"""
        return len(self.queue)

    async def get_jobs_by_status(self, status: JobStatus) -> list[Job]:
        """Get jobs by status"""
        return [job for job in self.jobs.values() if job.status == status]
