"""
Lifecycle management for async background tasks
Provides proper startup/shutdown hooks for background services
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import TaskRegistry

logger = get_logger(__name__)


class BackgroundTaskManager(TaskRegistry):
    """
    Coordinator-specific task manager, extending the shared TaskRegistry.
    Provides backward-compatible API for existing coordinator code.
    """

    async def start_task(self, name: str, coro, *args: Any, **kwargs: Any) -> None:
        """
        Start a background task

        Args:
            name: Task name for tracking
            coro: Coroutine function (not a coroutine object)
            *args: Arguments for coroutine
            **kwargs: Keyword arguments for coroutine
        """
        self.create_task(lambda: coro(*args, **kwargs), name=name)

    async def stop_task(self, name: str, timeout: float = 5.0) -> None:
        """Stop a specific background task"""
        await self.cancel(name, timeout=timeout)

    async def stop_all(self, timeout: float = 5.0) -> None:
        """Stop all background tasks"""
        await self.cancel_all(timeout=timeout)

    def get_task_status(self) -> dict[str, str]:
        """Get status of all managed tasks"""
        return self.get_status()


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
