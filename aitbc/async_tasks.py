"""
Async task lifecycle management
Provides task registry for tracking, logging, and cancelling background tasks.
Used by coordinator-api, blockchain-node, agent, and other services.
"""

import asyncio
from collections.abc import Callable
from threading import Lock
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
        self._lock = Lock()

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

        with self._lock:
            if name in self._tasks and not self._tasks[name].done():
                logger.warning("Task %s already running, skipping", name)
                return self._tasks[name]

            task = asyncio.create_task(_wrapped(), name=name)
            self._tasks[name] = task
            logger.info("Started background task: %s", name)
            return task

    async def cancel(self, name: str, timeout: float = 5.0) -> None:
        """Cancel a specific task and wait for it to finish."""
        with self._lock:
            task = self._tasks.get(name)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.CancelledError:
            pass
        except TimeoutError:
            logger.warning("Task %s did not cancel within %s seconds", name, timeout)

    async def cancel_all(self, timeout: float = 5.0) -> None:
        """Cancel all tracked tasks."""
        with self._lock:
            names = list(self._tasks.keys())
        for name in names:
            await self.cancel(name, timeout)
        with self._lock:
            self._tasks.clear()

    def track(self, task: asyncio.Task[Any], *, name: str) -> asyncio.Task[Any]:
        """Adopt an already-created task for status reporting and ``cancel_all``.

        Used by ``create_task_with_logging`` for fire-and-forget spawns that
        bypass ``create_task`` (which takes a callable, not a coroutine
        object). Without this, those tasks were invisible to shutdown
        cancellation (#1602). Done tasks are pruned once the registry grows
        past ``_TRACK_PRUNE_THRESHOLD`` so high-frequency per-request spawns
        cannot grow it without bound. If a live task is already registered
        under ``name``, the new task is left untracked rather than evicting
        the cancellable one.
        """
        with self._lock:
            if len(self._tasks) > _TRACK_PRUNE_THRESHOLD:
                self._tasks = {n: t for n, t in self._tasks.items() if not t.done()}
            existing = self._tasks.get(name)
            if existing is not None and not existing.done():
                logger.debug("Task %s already tracked; new task left untracked", name)
                return task
            self._tasks[name] = task
        return task

    def get_status(self) -> dict[str, str]:
        """Get status of all tracked tasks."""
        with self._lock:
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

# Prune done tasks from the global registry once it grows past this size so
# per-request fire-and-forget spawns cannot leak entries forever (#1602).
_TRACK_PRUNE_THRESHOLD = 512


def get_global_registry() -> TaskRegistry:
    """Get the global task registry."""
    return _global_registry


def create_task_with_logging(coro: Any, *, name: str) -> asyncio.Task[Any]:
    """Create a fire-and-forget background task with exception logging.

    Unlike ``TaskRegistry.create_task`` (which takes a callable), this
    accepts a coroutine object — matching the ``asyncio.create_task``
    signature — adds a done-callback that logs any unhandled exception,
    and registers the task with the global ``TaskRegistry`` so shutdown
    paths that call ``cancel_all`` can stop it (#1602).

    Use this for services that don't have a ``TaskRegistry`` instance but
    still need error visibility for background tasks.

    Args:
        coro: Coroutine object to run as a background task.
        name: Human-readable name for logging.

    Returns:
        The created asyncio.Task.
    """
    try:
        task = asyncio.create_task(coro, name=name)
    except RuntimeError:
        # No running event loop — close the coroutine to avoid
        # "coroutine was never awaited" warnings. The caller is
        # responsible for scheduling notifications in an async context.
        coro.close()
        raise

    def _log_exception(t: asyncio.Task[Any]) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Background task %s failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_log_exception)
    # Register with the global registry so lifespan shutdown can cancel
    # these tasks instead of letting them write after close_async_db (#1602).
    _global_registry.track(task, name=name)
    return task
