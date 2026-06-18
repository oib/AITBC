"""
Job Scheduler Module
Provides job scheduling for delayed and recurring tasks
"""

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class JobScheduler:
    """Job scheduler for delayed and recurring tasks"""

    def __init__(self):
        """Initialize job scheduler"""
        self.scheduled_jobs: dict[str, dict[str, Any]] = {}
        self.running = False
        self.task: asyncio.Task | None = None

    async def schedule(
        self,
        func: Callable,
        delay: float = 0,
        interval: float | None = None,
        job_id: str | None = None,
        args: tuple = (),
        kwargs: dict = None,
    ) -> str:
        """Schedule a job"""
        if job_id is None:
            job_id = str(uuid.uuid4())
        if kwargs is None:
            kwargs = {}
        run_at = time.time() + delay
        self.scheduled_jobs[job_id] = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "run_at": run_at,
            "interval": interval,
            "job_id": job_id,
        }
        return job_id

    async def cancel_scheduled_job(self, job_id: str) -> bool:
        """Cancel a scheduled job"""
        if job_id in self.scheduled_jobs:
            del self.scheduled_jobs[job_id]
            return True
        return False

    async def start(self) -> None:
        """Start the scheduler"""
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run_scheduler())

    async def stop(self) -> None:
        """Stop the scheduler"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _run_scheduler(self) -> None:
        """Run the scheduler loop"""
        while self.running:
            now = time.time()
            to_run = []
            for _job_id, job in list(self.scheduled_jobs.items()):
                if job["run_at"] <= now:
                    to_run.append(job)
            for job in to_run:
                try:
                    if asyncio.iscoroutinefunction(job["func"]):
                        await job["func"](*job["args"], **job["kwargs"])
                    else:
                        job["func"](*job["args"], **job["kwargs"])
                    if job["interval"]:
                        job["run_at"] = now + job["interval"]
                    else:
                        del self.scheduled_jobs[job["job_id"]]
                except Exception as e:
                    logger.error("Error running scheduled job %s: %s", job["job_id"], e)
                    if not job["interval"]:
                        del self.scheduled_jobs[job["job_id"]]
            await asyncio.sleep(0.1)
