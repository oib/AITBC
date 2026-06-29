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
        self._running = True
        for chain_id, entry in self._subscriptions.items():
            if entry.task is None or entry.task.done():
                entry.task = asyncio.create_task(
                    self._run_subscription(chain_id),
                    name=f"subscription_{chain_id}",
                )

    async def _run_subscription(self, chain_id: str) -> None:
        """Run a subscription with restart-on-failure logic."""
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
        self._running = False
        for entry in self._subscriptions.values():
            if entry.task and not entry.task.done():
                entry.task.cancel()
        for entry in self._subscriptions.values():
            if entry.task:
                try:
                    await entry.task
                except asyncio.CancelledError:
                    pass
