"""
Lifecycle management for async background tasks
Provides proper startup/shutdown hooks for background services
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class BackgroundTaskManager:
    """
    Manages lifecycle of background async tasks
    Ensures proper startup and graceful shutdown
    """

    def __init__(self) -> None:
        """Initialize task manager"""
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False

    async def start_task(self, name: str, coro, *args: Any, **kwargs: Any) -> None:
        """
        Start a background task

        Args:
            name: Task name for tracking
            coro: Coroutine to run
            *args: Arguments for coroutine
            **kwargs: Keyword arguments for coroutine
        """
        if name in self._tasks:
            logger.warning("Task %s already running, skipping", name)
            return

        task = asyncio.create_task(coro(*args, **kwargs), name=name)
        self._tasks[name] = task
        logger.info("Started background task: %s", name)

    async def stop_task(self, name: str, timeout: float = 5.0) -> None:
        """
        Stop a specific background task with timeout

        Args:
            name: Task name to stop
            timeout: Seconds to wait for graceful shutdown
        """
        if name not in self._tasks:
            logger.warning("Task %s not found, cannot stop", name)
            return

        task = self._tasks[name]
        task.cancel()

        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Task %s cancelled gracefully", name)
        except asyncio.TimeoutError:
            logger.warning("Task %s did not stop within %s seconds, forcing shutdown", name, timeout)
        finally:
            del self._tasks[name]

    async def stop_all(self, timeout: float = 5.0) -> None:
        """
        Stop all background tasks

        Args:
            timeout: Seconds to wait for each task to stop
        """
        logger.info("Stopping %s background tasks", len(self._tasks))
        for name in list(self._tasks.keys()):
            await self.stop_task(name, timeout)
        logger.info("All background tasks stopped")

    def get_task_status(self) -> dict[str, str]:
        """
        Get status of all managed tasks

        Returns:
            Dictionary mapping task names to their status
        """
        status = {}
        for name, task in self._tasks.items():
            if task.done():
                if task.cancelled():
                    status[name] = "cancelled"
                elif task.exception():
                    status[name] = f"error: {type(task.exception()).__name__}"
                else:
                    status[name] = "completed"
            else:
                status[name] = "running"
        return status


# Global task manager instance
_task_manager = BackgroundTaskManager()


def get_task_manager() -> BackgroundTaskManager:
    """Get global task manager instance"""
    return _task_manager


@asynccontextmanager
async def managed_lifespan(app: Any) -> AsyncIterator[None]:
    """
    Managed lifespan context with proper async task cleanup

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    logger.info("Starting application with managed lifecycle")
    try:
        # Startup phase
        logger.info("Startup phase complete")
        yield
    finally:
        # Shutdown phase
        logger.info("Shutdown phase: stopping background tasks")
        await _task_manager.stop_all()
        logger.info("Managed lifecycle shutdown complete")


class LifecycleState:
    """
    Tracks application lifecycle state
    """

    STARTING = "starting"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"

    def __init__(self) -> None:
        """Initialize lifecycle state"""
        self._state = self.STOPPED

    def set_state(self, state: str) -> None:
        """
        Set lifecycle state

        Args:
            state: New state value
        """
        logger.info("Lifecycle state transition: %s -> %s", self._state, state)
        self._state = state

    def get_state(self) -> str:
        """Get current lifecycle state"""
        return self._state

    def is_running(self) -> bool:
        """Check if application is running"""
        return self._state == self.RUNNING

    def is_shutting_down(self) -> bool:
        """Check if application is shutting down"""
        return self._state == self.SHUTTING_DOWN


# Global lifecycle state instance
_lifecycle_state = LifecycleState()


def get_lifecycle_state() -> LifecycleState:
    """Get global lifecycle state instance"""
    return _lifecycle_state
