"""
Worker Management Module
Provides worker pool and background task management
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class BackgroundTaskManager:
    """Manage background tasks"""

    def __init__(self, max_concurrent_tasks: int = 10):
        """Initialize background task manager"""
        self.max_concurrent_tasks = max_concurrent_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.tasks: dict[str, asyncio.Task] = {}
        self.task_info: dict[str, dict[str, Any]] = {}

    async def run_task(self, func: Callable, task_id: str | None = None, args: tuple = (), kwargs: dict = None) -> str:
        """Run a background task"""
        if task_id is None:
            task_id = str(uuid.uuid4())
        if kwargs is None:
            kwargs = {}

        async def wrapped_task():
            async with self.semaphore:
                try:
                    self.task_info[task_id]["status"] = "running"
                    self.task_info[task_id]["started_at"] = datetime.now(UTC)
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    self.task_info[task_id]["status"] = "completed"
                    self.task_info[task_id]["result"] = result
                    self.task_info[task_id]["completed_at"] = datetime.now(UTC)
                except Exception as e:
                    self.task_info[task_id]["status"] = "failed"
                    self.task_info[task_id]["error"] = str(e)
                    self.task_info[task_id]["completed_at"] = datetime.now(UTC)
                finally:
                    if task_id in self.tasks:
                        del self.tasks[task_id]

        self.task_info[task_id] = {
            "status": "pending",
            "created_at": datetime.now(UTC),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
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
            self.task_info[task_id]["completed_at"] = datetime.now(UTC)
            del self.tasks[task_id]
            return True
        return False

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get task status"""
        return self.task_info.get(task_id)

    async def get_all_tasks(self) -> dict[str, dict[str, Any]]:
        """Get all tasks"""
        return self.task_info.copy()

    async def wait_for_task(self, task_id: str, timeout: float | None = None) -> Any:
        """Wait for task completion"""
        if task_id not in self.tasks:
            raise ValueError(f"Task {task_id} not found")
        try:
            await asyncio.wait_for(self.tasks[task_id], timeout)
        except TimeoutError:
            await self.cancel_task(task_id)
            raise TimeoutError(f"Task {task_id} timed out") from None
        info = self.task_info.get(task_id)
        if info is None:
            raise ValueError(f"Task {task_id} info not found")
        if info["status"] == "failed":
            raise Exception(info["error"])
        return info["result"]


class WorkerPool:
    """Worker pool for parallel task execution"""

    def __init__(self, num_workers: int = 4):
        """Initialize worker pool"""
        self.num_workers = num_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
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
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

    async def submit(self, func: Callable, *args, **kwargs) -> Any:
        """Submit task to worker pool"""
        future: asyncio.Future[Any] = asyncio.Future()
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
                logger.error("Worker %s error: %s", worker_id, e)

    async def get_queue_size(self) -> int:
        """Get queue size"""
        return self.queue.qsize()
