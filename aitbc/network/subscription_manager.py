"""Subscription manager for multi-hub node support.

Manages multiple subscription clients, one per (chain_id, hub_url) pair.
Provides lifecycle management: add/remove subscriptions, start/stop all,
per-subscription restart on failure with configurable backoff.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from aitbc.async_tasks import create_task_with_logging

logger = logging.getLogger(__name__)


@runtime_checkable
class SubscriptionClientProtocol(Protocol):
    """Interface contract for subscription clients (implemented by Agent B)."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    @property
    def chain_id(self) -> str: ...

    @property
    def hub_url(self) -> str: ...

    @property
    def is_connected(self) -> bool: ...


@dataclass
class SubscriptionEntry:
    """Tracks a single subscription client instance."""

    client: SubscriptionClientProtocol
    task: asyncio.Task[None] | None = None
    restart_count: int = 0
    last_error: str = ""


class SubscriptionManager:
    """Manages multiple subscription clients, one per (chain_id, hub_url) pair.

    Provides lifecycle management: add/remove subscriptions, start/stop all,
    per-subscription restart on failure with configurable backoff.
    """

    def __init__(
        self,
        max_restarts: int = 3,
        restart_delay: float = 5.0,
    ) -> None:
        """Initialize the subscription manager.

        Args:
            max_restarts: Max restart attempts per subscription before giving up.
            restart_delay: Seconds to wait before restarting a failed subscription.
        """
        self._subscriptions: dict[str, SubscriptionEntry] = {}
        self._max_restarts = max_restarts
        self._restart_delay = restart_delay
        self._running = False
        self._lock = asyncio.Lock()

    def add_subscription(self, chain_id: str, client: SubscriptionClientProtocol) -> None:
        """Register a subscription client for a chain_id.

        Raises ValueError if a subscription for this chain_id already exists.
        """
        if chain_id in self._subscriptions:
            raise ValueError(f"Subscription for chain_id '{chain_id}' already exists")
        self._subscriptions[chain_id] = SubscriptionEntry(client=client)
        logger.info("Added subscription for chain %s (hub: %s)", chain_id, client.hub_url)

    def remove_subscription(self, chain_id: str) -> SubscriptionEntry | None:
        """Remove and return a subscription entry. Stops the task if running."""
        entry = self._subscriptions.pop(chain_id, None)
        if entry and entry.task and not entry.task.done():
            entry.task.cancel()
        return entry

    def get_subscription(self, chain_id: str) -> SubscriptionEntry | None:
        """Get the subscription entry for a chain_id."""
        return self._subscriptions.get(chain_id)

    def get_all_chains(self) -> list[str]:
        """Return all chain_ids with active subscriptions."""
        return list(self._subscriptions.keys())

    async def start_all(self) -> None:
        """Start all registered subscriptions as background tasks."""
        async with self._lock:
            self._running = True
            entries = list(self._subscriptions.items())
        for chain_id, entry in entries:
            if entry.task is None or entry.task.done():
                entry.task = create_task_with_logging(
                    self._run_subscription(chain_id),
                    name=f"subscription_{chain_id}",
                )

    async def _run_subscription(self, chain_id: str) -> None:
        """Run a subscription with restart-on-failure logic."""
        async with self._lock:
            if chain_id not in self._subscriptions:
                return
            entry = self._subscriptions[chain_id]
        while self._running and entry.restart_count <= self._max_restarts:
            try:
                await entry.client.start()
                break  # Normal exit
            except asyncio.CancelledError:
                break
            except Exception as e:
                entry.restart_count += 1
                entry.last_error = str(e)
                logger.warning(
                    "Subscription for chain %s failed (attempt %d/%d): %s",
                    chain_id,
                    entry.restart_count,
                    self._max_restarts,
                    e,
                )
                if entry.restart_count <= self._max_restarts:
                    await asyncio.sleep(self._restart_delay)
                else:
                    logger.error(
                        "Subscription for chain %s exhausted restarts (%d). Giving up.",
                        chain_id,
                        entry.restart_count,
                    )

    async def stop_all(self) -> None:
        """Stop all subscriptions and cancel tasks."""
        async with self._lock:
            self._running = False
            for entry in self._subscriptions.values():
                if entry.task and not entry.task.done():
                    entry.task.cancel()
            tasks = [(entry.task, entry.client) for entry in self._subscriptions.values() if entry.task]
        for task, client in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            if client.is_connected:
                try:
                    await client.stop()
                except Exception as e:
                    logger.warning("Error stopping subscription client for %s: %s", client.chain_id, e)
