"""
Async task lifecycle management
Provides task registry for tracking, logging, and cancelling background tasks.
Used by coordinator-api, blockchain-node, agent, and other services.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class TaskRegistry:
    """
    Registry for tracking asyncio background tasks.
    Ensures tasks are logged on failure and cancelled cleanly on shutdown.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def create_task(
        self,
        coro: Callable[[], Any],
        *,
        name: str,
        restart: bool = False,
        restart_delay: float = 1.0,
    ) -> asyncio.Task[Any]:
        """
        Create and track a background task.

        Args:
            coro: Coroutine function to run (not a coroutine object)
            name: Unique name for tracking
            restart: If True, restart the task automatically on failure
            restart_delay: Seconds to wait before restarting

        Returns:
            The created asyncio.Task
        """
        if name in self._tasks and not self._tasks[name].done():
            logger.warning("Task %s already running, skipping", name)
            return self._tasks[name]

        async def _wrapped() -> Any:
            while True:
                try:
                    return await coro()
                except asyncio.CancelledError:
                    logger.info("Task %s cancelled", name)
                    raise
                except Exception as exc:
                    logger.error("Task %s failed: %s", name, exc, exc_info=True)
                    if not restart:
                        raise
                    logger.info("Restarting task %s in %.1f seconds", name, restart_delay)
                    await asyncio.sleep(restart_delay)

        task = asyncio.create_task(_wrapped(), name=name)
        self._tasks[name] = task
        logger.info("Started background task: %s", name)
        return task

    async def cancel(self, name: str, timeout: float = 5.0) -> None:
        """Cancel a specific task and wait for it to finish."""
        task = self._tasks.get(name)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.warning("Task %s did not cancel within %s seconds", name, timeout)

    async def cancel_all(self, timeout: float = 5.0) -> None:
        """Cancel all tracked tasks."""
        for name in list(self._tasks.keys()):
            await self.cancel(name, timeout)
        self._tasks.clear()

    def get_status(self) -> dict[str, str]:
        """Get status of all tracked tasks."""
        status: dict[str, str] = {}
        for name, task in self._tasks.items():
            if task.done():
                if task.cancelled():
                    status[name] = "cancelled"
                elif task.exception():
                    exc = task.exception()
                    status[name] = f"error: {type(exc).__name__}" if exc else "error"
                else:
                    status[name] = "completed"
            else:
                status[name] = "running"
        return status


# Global registry for convenience (use per-module registry for isolation)
_global_registry = TaskRegistry()


def get_global_registry() -> TaskRegistry:
    """Get the global task registry."""
    return _global_registry
