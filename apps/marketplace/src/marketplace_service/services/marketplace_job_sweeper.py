"""Generic marketplace job payment sweeper (v0.25.7 first-class IPFS).

Handles escrow release and refund for MarketplaceJob / MarketplaceJobPayment
records.  Keeps the marketplace service self-contained and does not rely on the
coordinator's StuckEscrowSweeper.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.marketplace import BlockchainRPCClient

from ..config import settings
from ..domain.marketplace import MarketplaceJob, MarketplaceJobPayment
from ..storage import get_session_context

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def _default_session_factory() -> AbstractAsyncContextManager[AsyncSession]:
    return get_session_context()


class MarketplaceJobSweeper:
    """Release or refund escrow for marketplace jobs based on state and age."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        batch_size: int | None = None,
        min_age_seconds: int | None = None,
        refund_grace_seconds: int | None = None,
        rpc_client: BlockchainRPCClient | None = None,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("MARKETPLACE_JOB_SWEEP_INTERVAL_SECONDS", 300)
        self.batch_size = batch_size or _env_int("MARKETPLACE_JOB_SWEEP_BATCH_SIZE", 50)
        # Give normal cancel/fail/expire handlers time to settle on their own.
        self.min_age_seconds = min_age_seconds or _env_int("MARKETPLACE_JOB_SWEEP_MIN_AGE_SECONDS", 60)
        # Extra grace after expires_at before releasing to the provider.
        self.refund_grace_seconds = refund_grace_seconds or _env_int("MARKETPLACE_JOB_SWEEP_GRACE_SECONDS", 60)
        self._rpc_client = rpc_client or BlockchainRPCClient(
            rpc_url=settings.blockchain_rpc_url,
            api_key=settings.blockchain_rpc_api_key,
        )
        self._session_factory = session_factory or _default_session_factory
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the background sweep loop."""
        if self._task is not None and not self._task.done():
            logger.warning("MarketplaceJobSweeper is already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "MarketplaceJobSweeper started (interval=%ss, batch=%s)",
            self.interval_seconds,
            self.batch_size,
        )

    async def stop(self) -> None:
        """Stop the background sweep loop."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        logger.info("MarketplaceJobSweeper stopped")

    async def _run(self) -> None:
        """Main loop; runs until stop() is called."""
        while not self._stop_event.is_set():
            try:
                await self.sweep_once()
            except Exception:
                logger.exception("MarketplaceJobSweeper iteration failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self.interval_seconds),
                )
            except asyncio.TimeoutError:
                pass

    async def sweep_once(self) -> dict[str, int]:
        """Run one sweep and return counts."""
        counts = {"released": 0, "refunded": 0, "failed": 0}

        async with self._session_factory() as session:
            # 1. Release: jobs that completed or expired and are past the grace period.
            now = datetime.now(UTC)
            release_cutoff = now - timedelta(seconds=self.refund_grace_seconds)

            release_stmt = (
                select(MarketplaceJob, MarketplaceJobPayment)
                .join(MarketplaceJobPayment, col(MarketplaceJob.payment_id) == MarketplaceJobPayment.id)
                .where(col(MarketplaceJobPayment.status) == "escrowed")
                .where(col(MarketplaceJobPayment.escrowed_at).is_not(None))
                .where(col(MarketplaceJob.state).in_({"COMPLETED", "EXPIRED"}))
                .where((col(MarketplaceJob.expires_at).is_(None)) | (col(MarketplaceJob.expires_at) < release_cutoff))
                .limit(self.batch_size)
            )
            release_result = await session.execute(release_stmt)
            for job, payment in release_result.all():
                if payment is None:
                    continue
                try:
                    released = await self._release_payment(session, job, payment)
                    if released:
                        counts["released"] += 1
                    else:
                        counts["failed"] += 1
                except Exception:
                    logger.exception("Failed to release payment for job %s", job.id)
                    counts["failed"] += 1

            # 2. Refund: failed/canceled jobs or payments already marked refund_pending.
            min_age = now - timedelta(seconds=self.min_age_seconds)

            refund_stmt = (
                select(MarketplaceJob, MarketplaceJobPayment)
                .join(MarketplaceJobPayment, col(MarketplaceJob.payment_id) == MarketplaceJobPayment.id)
                .where(col(MarketplaceJobPayment.status).in_({"escrowed", "refund_pending"}))
                .where(col(MarketplaceJobPayment.escrowed_at).is_not(None))
                .where(
                    (col(MarketplaceJob.state).in_({"FAILED", "CANCELED"}))
                    | (col(MarketplaceJobPayment.status) == "refund_pending")
                )
                .where(col(MarketplaceJob.updated_at) < min_age)
                .limit(self.batch_size)
            )
            refund_result = await session.execute(refund_stmt)
            for job, payment in refund_result.all():
                if payment is None:
                    continue
                try:
                    refunded = await self._refund_payment(session, job, payment)
                    if refunded:
                        counts["refunded"] += 1
                    else:
                        counts["failed"] += 1
                except Exception:
                    logger.exception("Failed to refund payment for job %s", job.id)
                    counts["failed"] += 1

            await session.commit()

        logger.info(
            "MarketplaceJobSweeper finished: released=%s, refunded=%s, failed=%s",
            counts["released"],
            counts["refunded"],
            counts["failed"],
        )
        return counts

    async def _release_payment(
        self,
        session: AsyncSession,
        job: MarketplaceJob,
        payment: MarketplaceJobPayment,
    ) -> bool:
        """Release escrow to the provider. Returns True on success."""
        if not job.escrow_contract_id:
            logger.warning("Job %s has no escrow_contract_id; skipping release", job.id)
            job.state = "FAILED"
            job.error = "missing escrow_contract_id"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            return False

        result = await self._rpc_client.release_escrow(job.escrow_contract_id)
        if result and result.get("success"):
            tx_hash = str(result.get("tx_hash", ""))
            job.state = "RELEASED"
            job.payment_status = "released"
            job.tx_hash = tx_hash
            job.updated_at = datetime.now(UTC)

            payment.status = "released"
            payment.transaction_hash = tx_hash
            payment.released_at = datetime.now(UTC)
            payment.updated_at = datetime.now(UTC)

            session.add(job)
            session.add(payment)
            return True

        logger.warning("Escrow release for job %s was not successful: %s", job.id, result)
        payment.status = "settlement_failed"
        payment.updated_at = datetime.now(UTC)
        job.payment_status = "settlement_failed"
        job.error = f"release failed: {result}"
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.add(payment)
        return False

    async def _refund_payment(
        self,
        session: AsyncSession,
        job: MarketplaceJob,
        payment: MarketplaceJobPayment,
    ) -> bool:
        """Refund escrow to the buyer. Returns True on success."""
        if not job.escrow_contract_id:
            logger.warning("Job %s has no escrow_contract_id; skipping refund", job.id)
            job.state = "FAILED"
            job.error = "missing escrow_contract_id"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            return False

        result = await self._rpc_client.refund_escrow(job.escrow_contract_id)
        if result and result.get("success"):
            tx_hash = str(result.get("tx_hash", ""))
            job.state = "REFUNDED"
            job.payment_status = "refunded"
            job.refund_tx_hash = tx_hash
            job.error = job.error or "refunded by sweeper"
            job.updated_at = datetime.now(UTC)

            payment.status = "refunded"
            payment.refund_transaction_hash = tx_hash
            payment.refunded_at = datetime.now(UTC)
            payment.updated_at = datetime.now(UTC)

            session.add(job)
            session.add(payment)
            return True

        logger.warning("Escrow refund for job %s was not successful: %s", job.id, result)
        payment.status = "settlement_failed"
        payment.updated_at = datetime.now(UTC)
        job.payment_status = "settlement_failed"
        job.error = f"refund failed: {result}"
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.add(payment)
        return False
