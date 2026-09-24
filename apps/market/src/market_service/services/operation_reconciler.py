"""Operation ledger reconciler for the market service.

Mirrors the sweeper pattern (``MarketJobSweeper``): a periodic task that
expires stale ``pending`` operation rows and purges terminal rows past
retention. Rows that cannot be safely re-driven (``allow_adopt=False``)
become ``uncertain`` and wait for operator resolution rather than risking a
double-apply.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from aitbc.aitbc_logging import get_logger
from aitbc.operations import OperationLedger

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


class OperationReconciler:
    """Expire stale pending operations and purge old terminal rows."""

    def __init__(
        self,
        ledger_factory: Callable[[], OperationLedger],
        interval_seconds: int | None = None,
        retention_seconds: int | None = None,
    ) -> None:
        self._ledger_factory = ledger_factory
        self.interval_seconds = interval_seconds or _env_int("MARKET_OPS_SWEEP_INTERVAL_SECONDS", 300)
        self.retention_seconds = retention_seconds or _env_int("MARKET_OPS_RETENTION_SECONDS", 7 * 86400)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="operation-reconciler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        ledger = self._ledger_factory()
        while True:
            try:
                report = await ledger.reconcile_async()
                purged = await asyncio.to_thread(ledger.purge, self.retention_seconds)
                if report["expired_to_failed"] or report["expired_to_uncertain"] or purged:
                    logger.info("Operation reconcile: %s purged=%d", report, purged)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Operation ledger reconciliation failed")
            await asyncio.sleep(self.interval_seconds)
