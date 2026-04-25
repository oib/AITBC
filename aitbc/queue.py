"""
Queue utilities for AITBC
Provides task queue helpers, job scheduling, and background task management
"""

import asyncio
import heapq
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid


T = TypeVar('T')


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
    job_id: str = field(compare=False)
    func: Callable = field(compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    status: JobStatus = field(default=JobStatus.PENDING, compare=False)
    created_at: datetime = field(default_factory=datetime.utcnow, compare=False)
    started_at: Optional[datetime] = field(default=None, compare=False)
    completed_at: Optional[datetime] = field(default=None, compare=False)
    result: Any = field(default=None, compare=False)
    error: Optional[str] = field(default=None, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=3, compare=False)
    
    def __post_init__(self):
        if self.job_id is None:
            self.job_id = str(uuid.uuid4())


class TaskQueue:
    """Priority-based task queue"""
    
    def __init__(self):
        """Initialize task queue"""
        self.queue: List[Job] = []
        self.jobs: Dict[str, Job] = {}
        self.lock = asyncio.Lock()
    
    async def enqueue(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        priority: JobPriority = JobPriority.MEDIUM,
        max_retries: int = 3
    ) -> str:
        """Enqueue a task"""
        if kwargs is None:
            kwargs = {}
        
        job = Job(
            priority=priority.value,
            func=func,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries
        )
        
        async with self.lock:
            heapq.heappush(self.queue, job)
            self.jobs[job.job_id] = job
        
        return job.job_id
    
    async def dequeue(self) -> Optional[Job]:
        """Dequeue a task"""
        async with self.lock:
            if not self.queue:
                return None
            
            job = heapq.heappop(self.queue)
            return job
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        return self.jobs.get(job_id)
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        async with self.lock:
            job = self.jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                # Remove from queue
                self.queue = [j for j in self.queue if j.job_id != job_id]
                heapq.heapify(self.queue)
                return True
        return False
    
    async def get_queue_size(self) -> int:
        """Get queue size"""
        return len(self.queue)
    
    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        """Get jobs by status"""
        return [job for job in self.jobs.values() if job.status == status]


class JobScheduler:
    """Job scheduler for delayed and recurring tasks"""
    
    def __init__(self):
        """Initialize job scheduler"""
        self.scheduled_jobs: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def schedule(
        self,
        func: Callable,
        delay: float = 0,
        interval: Optional[float] = None,
        job_id: Optional[str] = None,
        args: tuple = (),
        kwargs: dict = None
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
            "job_id": job_id
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
            
            for job_id, job in list(self.scheduled_jobs.items()):
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
                    print(f"Error running scheduled job {job['job_id']}: {e}")
                    if not job["interval"]:
                        del self.scheduled_jobs[job["job_id"]]
            
            await asyncio.sleep(0.1)


class BackgroundTaskManager:
    """Manage background tasks"""
    
    def __init__(self, max_concurrent_tasks: int = 10):
        """Initialize background task manager"""
        self.max_concurrent_tasks = max_concurrent_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.tasks: Dict[str, asyncio.Task] = {}
        self.task_info: Dict[str, Dict[str, Any]] = {}
    
    async def run_task(
        self,
        func: Callable,
        task_id: Optional[str] = None,
        args: tuple = (),
        kwargs: dict = None
    ) -> str:
        """Run a background task"""
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        if kwargs is None:
            kwargs = {}
        
        async def wrapped_task():
            async with self.semaphore:
                try:
                    self.task_info[task_id]["status"] = "running"
                    self.task_info[task_id]["started_at"] = datetime.utcnow()
                    
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    self.task_info[task_id]["status"] = "completed"
                    self.task_info[task_id]["result"] = result
                    self.task_info[task_id]["completed_at"] = datetime.utcnow()
                except Exception as e:
                    self.task_info[task_id]["status"] = "failed"
                    self.task_info[task_id]["error"] = str(e)
                    self.task_info[task_id]["completed_at"] = datetime.utcnow()
                finally:
                    if task_id in self.tasks:
                        del self.tasks[task_id]
        
        self.task_info[task_id] = {
            "status": "pending",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None
        }
        
        task = asyncio.create_task(wrapped_task())
        self.tasks[task_id] = task
        
        return task_id
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a background task"""
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
            try:
                await self.tasks[task_id]
            except asyncio.CancelledError:
                pass
            
            self.task_info[task_id]["status"] = "cancelled"
            self.task_info[task_id]["completed_at"] = datetime.utcnow()
            del self.tasks[task_id]
            return True
        return False
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        return self.task_info.get(task_id)
    
    async def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all tasks"""
        return self.task_info.copy()
    
    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """Wait for task completion"""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        
        try:
            await asyncio.wait_for(self.tasks[task_id], timeout)
        except asyncio.TimeoutError:
            await self.cancel_task(task_id)
            raise TimeoutError(f"Task {task_id} timed out")
        
        info = self.task_info.get(task_id)
        if info["status"] == "failed":
            raise Exception(info["error"])
        
        return info["result"]


class WorkerPool:
    """Worker pool for parallel task execution"""
    
    def __init__(self, num_workers: int = 4):
        """Initialize worker pool"""
        self.num_workers = num_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: List[asyncio.Task] = []
        self.running = False
    
    async def start(self) -> None:
        """Start worker pool"""
        if self.running:
            return
        
        self.running = True
        for i in range(self.num_workers):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
    
    async def stop(self) -> None:
        """Stop worker pool"""
        self.running = False
        
        # Cancel all workers
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
    
    async def submit(self, func: Callable, *args, **kwargs) -> Any:
        """Submit task to worker pool"""
        future = asyncio.Future()
        await self.queue.put((func, args, kwargs, future))
        return await future
    
    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine"""
        while self.running:
            try:
                func, args, kwargs, future = await self.queue.get()
                
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker {worker_id} error: {e}")
    
    async def get_queue_size(self) -> int:
        """Get queue size"""
        return self.queue.qsize()


def debounce(delay: float = 0.5):
    """Decorator to debounce function calls"""
    def decorator(func: Callable) -> Callable:
        last_called = [0]
        timer = [None]
        
        async def wrapped(*args, **kwargs):
            async def call():
                await asyncio.sleep(delay)
                if asyncio.get_event_loop().time() - last_called[0] >= delay:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
            
            last_called[0] = asyncio.get_event_loop().time()
            if timer[0]:
                timer[0].cancel()
            
            timer[0] = asyncio.create_task(call())
            return await timer[0]
        
        return wrapped
    return decorator


def throttle(calls_per_second: float = 1.0):
    """Decorator to throttle function calls"""
    def decorator(func: Callable) -> Callable:
        min_interval = 1.0 / calls_per_second
        last_called = [0]
        
        async def wrapped(*args, **kwargs):
            now = asyncio.get_event_loop().time()
            elapsed = now - last_called[0]
            
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            
            last_called[0] = asyncio.get_event_loop().time()
            
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapped
    return decorator
