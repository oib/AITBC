"""Background timeout monitor for legacy cross-chain settlement records."""

from __future__ import annotations

import asyncio

from sqlalchemy.exc import SQLAlchemyError

from aitbc.async_tasks import create_task_with_logging

from ..logger import get_logger
from .settlement import CrossChainSettlementService

logger = get_logger(__name__)

# Interval between timeout checks in the background monitor loop.
_MONITOR_INTERVAL_SECONDS = 10

# Expected failure surface for the settlement-service calls below: SQLAlchemy
# driver errors, OS/asyncio transport errors, lazy imports, JSON/data-shape
# decode, HTLC/proof ValueErrors and Decimal arithmetic on untrusted amounts.
# Genuine BaseExceptions (incl. asyncio.CancelledError) still propagate (#1860).
_SERVICE_ERRORS = (
    ImportError,
    SQLAlchemyError,
    ArithmeticError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
)


class AtomicSettlementCoordinator:
    """Run timeout checks for legacy cross-chain settlement records."""

    def __init__(self, chain_id: str):
        self.chain_id = chain_id
        self._service = CrossChainSettlementService(chain_id)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start_monitor(self) -> None:
        """Start background timeout monitor task.

        Launches ``_monitor_loop`` as an asyncio background task. The loop
        runs every 10 seconds, calling
        ``CrossChainSettlementService.check_timeouts()`` and refunding any
        escrows that have exceeded their timeout. Safe to call multiple
        times — if a monitor is already running, this is a no-op.
        """
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        # Startup recovery: refund escrows that timed out while the node was
        # down, before entering the periodic loop. Escrows still within their
        # timeout are left for the loop to refund when they expire.
        try:
            recovered = await self._service.check_timeouts()
            if recovered:
                logger.info("Startup recovery refunded %d timed-out escrows: %s", len(recovered), recovered)
        except _SERVICE_ERRORS as e:
            logger.error("Startup recovery scan failed: %s", e)
        self._task = create_task_with_logging(self._monitor_loop(), name="settlement_monitor_loop")
        logger.info("Settlement timeout monitor started (interval=%ds)", _MONITOR_INTERVAL_SECONDS)

    async def stop_monitor(self) -> None:
        """Stop background timeout monitor task.

        Cancels the monitor task and waits for it to finish. Safe to call
        when no monitor is running.
        """
        if not self._running:
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Settlement timeout monitor stopped")

    async def _monitor_loop(self) -> None:
        """Background loop that checks timeouts every 10 seconds.

        On each tick, calls ``check_timeouts()`` which returns a list of
        escrow IDs that were refunded. The loop logs the count and sleeps
        for ``_MONITOR_INTERVAL_SECONDS`` before the next tick. The loop
        exits cleanly when ``_running`` is set to False or the task is
        cancelled.
        """
        logger.info("Monitor loop started")
        try:
            while self._running:
                try:
                    refunded = await self._service.check_timeouts()
                    if refunded:
                        logger.info("Monitor refunded %d timed-out escrows: %s", len(refunded), refunded)
                except _SERVICE_ERRORS as e:
                    logger.error("Monitor loop error during timeout check: %s", e)

                await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Monitor loop cancelled")
            raise
        except _SERVICE_ERRORS as e:
            logger.error("Monitor loop crashed: %s", e)
            raise
        finally:
            self._running = False
