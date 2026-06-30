"""Atomic settlement coordinator (v0.9.0 B8).

Orchestrates the full cross-chain atomic settlement lifecycle as a
background asyncio task. The coordinator wraps ``CrossChainSettlementService``
(B3) and drives a trade through the complete happy path:

    create_escrow → lock_escrow → verify_lock → execute_trade → settle

If any step fails or the escrow times out, the coordinator triggers a
refund on both chains. A background monitor loop runs every 10 seconds to
check for timed-out escrows and refund them automatically.

This is the integration layer between the trading service (which decides
*what* to settle) and the settlement service (which knows *how* to settle).
"""

from __future__ import annotations

import asyncio

from ..logger import get_logger
from .settlement import CrossChainSettlementService

logger = get_logger(__name__)

# Interval between timeout checks in the background monitor loop.
_MONITOR_INTERVAL_SECONDS = 10


class AtomicSettlementCoordinator:
    """Orchestrates atomic cross-chain settlement lifecycle (v0.9.0 B8).

    Runs as a background asyncio task that monitors pending escrows and
    advances them through the lifecycle:
    1. create_escrow → escrow_id
    2. lock_escrow → source chain locked
    3. verify_lock → destination verifies lock proof
    4. execute_trade → trade executed on destination
    5. settle (happy path) OR refund (timeout path)
    """

    def __init__(self, chain_id: str = "ait-hub"):
        self.chain_id = chain_id
        self._service = CrossChainSettlementService(chain_id)
        self._running = False
        self._task: asyncio.Task | None = None

    async def run_settlement(
        self,
        trade_id: str,
        source_chain: str,
        dest_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        timeout_seconds: int | None = None,
    ) -> dict:
        """Run full settlement lifecycle for a trade.

        Executes the happy path: create → lock → verify → execute → settle.
        If any step fails, the escrow is left in its current state (the
        background monitor will refund it on timeout) and a failure result
        is returned.

        Returns:
            ``{"escrow_id": ..., "status": "completed", "secret": ...}`` on
            success, or ``{"escrow_id": ..., "status": "failed", "error": ...}``
            on failure.
        """
        escrow_id: str | None = None
        secret: str = ""

        try:
            # Step 1: Create escrow
            create_result = await self._service.create_escrow(
                trade_id=trade_id,
                source_chain=source_chain,
                dest_chain=dest_chain,
                sender=sender,
                recipient=recipient,
                amount=amount,
                timeout_seconds=timeout_seconds,
            )
            escrow_id = create_result["escrow_id"]
            secret = create_result.get("secret", "")
            logger.info("Settlement %s: escrow created for trade %s", escrow_id, trade_id)

            # Step 2: Lock funds on source chain
            await self._service.lock_escrow(escrow_id)
            logger.info("Settlement %s: locked on source chain", escrow_id)

            # Step 3: Verify lock on destination chain
            await self._service.verify_lock(escrow_id)
            logger.info("Settlement %s: lock verified on destination", escrow_id)

            # Step 4: Execute trade on destination chain
            await self._service.execute_trade(escrow_id)
            logger.info("Settlement %s: trade executed on destination", escrow_id)

            # Step 5: Settle (reveal secret, release on both chains)
            await self._service.settle(escrow_id, secret)
            logger.info("Settlement %s: completed (secret revealed)", escrow_id)

            return {
                "escrow_id": escrow_id,
                "status": "completed",
                "secret": secret,
            }

        except Exception as e:
            logger.error("Settlement %s failed: %s", escrow_id or "?", e)
            # Attempt refund if the escrow was created but not yet completed.
            if escrow_id is not None:
                try:
                    await self._service.refund(escrow_id)
                    logger.info("Settlement %s: refunded after failure", escrow_id)
                except Exception as refund_err:
                    logger.error("Settlement %s: refund also failed: %s", escrow_id, refund_err)

            return {
                "escrow_id": escrow_id,
                "status": "failed",
                "error": str(e),
            }

    async def run_refund(self, escrow_id: str) -> dict:
        """Trigger refund for an escrow (timeout or manual).

        Delegates to ``CrossChainSettlementService.refund()``. Use this for
        manual refund triggers (e.g., dispute resolution) — the background
        monitor handles timeout refunds automatically.

        Returns:
            Refund result dict from the settlement service.
        """
        logger.info("Manual refund triggered for escrow %s", escrow_id)
        return await self._service.refund(escrow_id)

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
        self._task = asyncio.create_task(self._monitor_loop())
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
                except Exception as e:
                    logger.error("Monitor loop error during timeout check: %s", e)

                await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Monitor loop cancelled")
            raise
        except Exception as e:
            logger.error("Monitor loop crashed: %s", e)
            raise
        finally:
            self._running = False
