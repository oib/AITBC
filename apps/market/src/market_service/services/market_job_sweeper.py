"""Generic market job payment sweeper (v0.25.7 first-class IPFS).

Handles escrow release and refund for MarketJob / MarketJobPayment
records.  Keeps the market service self-contained and does not rely on the
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
from aitbc.market import BlockchainRPCClient

from ..config import settings
from ..domain.market import MarketJob, MarketJobPayment
from ..storage import get_session_context

logger = get_logger(__name__)

# A 'not yet' settlement answer (404, {success:false}, or any raised error)
# defers a job's escrow only this long before one confirming read decides
# its fate. Six hours mirrors the coordinator's 425-deferral bound: far
# above follower lag and any restart window, bounded churn instead of
# either instant-terminal or forever-silent.
DEFAULT_SETTLE_DEFERRAL_MAX_SECONDS = 6 * 3600
META_SETTLE_DEFERRAL_FIRST_AT = "settle_deferral_first_at"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def _default_session_factory() -> AbstractAsyncContextManager[AsyncSession]:
    return get_session_context()


class MarketJobSweeper:
    """Release or refund escrow for market jobs based on state and age."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        batch_size: int | None = None,
        min_age_seconds: int | None = None,
        refund_grace_seconds: int | None = None,
        settle_max_seconds: int | None = None,
        rpc_client: BlockchainRPCClient | None = None,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self.settle_max_seconds = settle_max_seconds or _env_int(
            "MARKET_JOB_SWEEP_SETTLE_MAX_SECONDS", DEFAULT_SETTLE_DEFERRAL_MAX_SECONDS
        )
        self.interval_seconds = interval_seconds or _env_int("MARKET_JOB_SWEEP_INTERVAL_SECONDS", 300)
        self.batch_size = batch_size or _env_int("MARKET_JOB_SWEEP_BATCH_SIZE", 50)
        # Give normal cancel/fail/expire handlers time to settle on their own.
        self.min_age_seconds = min_age_seconds or _env_int("MARKET_JOB_SWEEP_MIN_AGE_SECONDS", 60)
        # Extra grace after expires_at before releasing to the provider.
        self.refund_grace_seconds = refund_grace_seconds or _env_int("MARKET_JOB_SWEEP_GRACE_SECONDS", 60)
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
            logger.warning("MarketJobSweeper is already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "MarketJobSweeper started (interval=%ss, batch=%s)",
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
        logger.info("MarketJobSweeper stopped")

    async def _run(self) -> None:
        """Main loop; runs until stop() is called."""
        while not self._stop_event.is_set():
            try:
                await self.sweep_once()
            except Exception:
                logger.exception("MarketJobSweeper iteration failed")
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
                select(MarketJob, MarketJobPayment)
                .join(MarketJobPayment, col(MarketJob.payment_id) == MarketJobPayment.id)
                .where(col(MarketJobPayment.status) == "escrowed")
                .where(col(MarketJobPayment.escrowed_at).is_not(None))
                .where(col(MarketJob.state).in_({"COMPLETED", "EXPIRED"}))
                .where((col(MarketJob.expires_at).is_(None)) | (col(MarketJob.expires_at) < release_cutoff))
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
                select(MarketJob, MarketJobPayment)
                .join(MarketJobPayment, col(MarketJob.payment_id) == MarketJobPayment.id)
                .where(col(MarketJobPayment.status).in_({"escrowed", "refund_pending"}))
                .where(col(MarketJobPayment.escrowed_at).is_not(None))
                .where((col(MarketJob.state).in_({"FAILED", "CANCELED"})) | (col(MarketJobPayment.status) == "refund_pending"))
                .where(col(MarketJob.updated_at) < min_age)
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
            "MarketJobSweeper finished: released=%s, refunded=%s, failed=%s",
            counts["released"],
            counts["refunded"],
            counts["failed"],
        )
        return counts

    async def _release_payment(
        self,
        session: AsyncSession,
        job: MarketJob,
        payment: MarketJobPayment,
    ) -> bool:
        """Release escrow to the provider. Returns True on success."""
        if not job.escrow_contract_id:
            logger.warning("Job %s has no escrow_contract_id; skipping release", job.id)
            job.state = "FAILED"
            job.error = "missing escrow_contract_id"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            return False

        try:
            result = await self._rpc_client.release_escrow(job.escrow_contract_id)
        except Exception as e:
            # Any raised answer (425 'lock not sealed', 5xx, transport) is a
            # 'not yet' too -- it shares the bounded deferral instead of
            # retrying forever and silently.
            return await self._settlement_not_yet(session, job, payment, f"{type(e).__name__}: {e}", job.escrow_contract_id)
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
            self._clear_deferral(payment)

            session.add(job)
            session.add(payment)
            return True

        # Falsy answers are 'not yet': a 404 means 'no escrow row on the node
        # asked' (absent, wrong node, or a lag), {success:false} is the node's
        # rolled-back retryable reply. Neither may go terminal in one pass.
        outcome = (
            "no escrow row on the queried node (404)"
            if result is None
            else f"rolled back by the node, retryable ({result.get('message')})"
        )
        return await self._settlement_not_yet(session, job, payment, outcome, job.escrow_contract_id)

    async def _refund_payment(
        self,
        session: AsyncSession,
        job: MarketJob,
        payment: MarketJobPayment,
    ) -> bool:
        """Refund escrow to the buyer. Returns True on success."""
        if not job.escrow_contract_id:
            logger.warning("Job %s has no escrow_contract_id; skipping refund", job.id)
            job.state = "FAILED"
            job.error = "missing escrow_contract_id"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            return False

        try:
            result = await self._rpc_client.refund_escrow(job.escrow_contract_id)
        except Exception as e:
            return await self._settlement_not_yet(session, job, payment, f"{type(e).__name__}: {e}", job.escrow_contract_id)
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
            self._clear_deferral(payment)

            session.add(job)
            session.add(payment)
            return True

        outcome = (
            "no escrow row on the queried node (404)"
            if result is None
            else f"rolled back by the node, retryable ({result.get('message')})"
        )
        return await self._settlement_not_yet(session, job, payment, outcome, job.escrow_contract_id)

    @staticmethod
    def _clear_deferral(payment: MarketJobPayment) -> None:
        """A definitive answer ends the deferral streak."""
        meta = dict(payment.meta_data or {})
        if meta.pop(META_SETTLE_DEFERRAL_FIRST_AT, None) is not None:
            payment.meta_data = meta

    async def _settlement_not_yet(
        self,
        session: AsyncSession,
        job: MarketJob,
        payment: MarketJobPayment,
        outcome: str,
        contract_id: str,
    ) -> bool:
        """A 'not yet' settlement answer defers, bounded by settle_max_seconds.

        Inside the bound the row stays selectable and the next sweep retries;
        the first deferral stamps ``meta_data['settle_deferral_first_at']``.
        Past the bound one ``GET /escrow/{id}`` read converts the guess into
        evidence: absent -> terminal ``settlement_failed``; a released or
        refunded row -> adopt that verdict; anything else (still locked, or
        the read itself failed) -> keep deferring with a loud log line.
        """
        now = datetime.now(UTC)
        meta = dict(payment.meta_data or {})
        first_at: datetime | None = None
        raw = meta.get(META_SETTLE_DEFERRAL_FIRST_AT)
        if raw:
            try:
                first_at = datetime.fromisoformat(str(raw))
                if first_at.tzinfo is None:
                    first_at = first_at.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                first_at = None
        if first_at is None:
            meta[META_SETTLE_DEFERRAL_FIRST_AT] = now.isoformat()
            payment.meta_data = meta
            payment.updated_at = now
            session.add(payment)
            logger.warning(
                "Escrow settlement for job %s payment %s deferred (%s); retrying on next sweep",
                job.id,
                payment.id,
                outcome,
            )
            return False
        elapsed = (now - first_at).total_seconds()
        if elapsed <= self.settle_max_seconds:
            logger.warning(
                "Escrow settlement for job %s payment %s still deferred after %.0fs (%s)",
                job.id,
                payment.id,
                elapsed,
                outcome,
            )
            return False

        # Past the bound: one read decides -- never terminal on a guess.
        escrow: dict[str, Any] | None = None
        read_error: Exception | None = None
        try:
            escrow = await self._rpc_client.verify_escrow(contract_id)
        except Exception as e:
            read_error = e
        if read_error is None and escrow is None:
            meta.pop(META_SETTLE_DEFERRAL_FIRST_AT, None)
            payment.meta_data = meta
            payment.status = "settlement_failed"
            payment.updated_at = now
            job.payment_status = "settlement_failed"
            job.error = f"settlement deferred {elapsed:.0f}s past bound ({outcome}); escrow confirmed absent"
            job.updated_at = now
            session.add(job)
            session.add(payment)
            logger.error(
                "Escrow settlement for job %s payment %s deferred %.0fs past the %ss bound "
                "and the escrow is confirmed absent -- marking settlement_failed",
                job.id,
                payment.id,
                elapsed,
                self.settle_max_seconds,
            )
            return False
        if read_error is None and escrow is not None and escrow.get("state") in {"released", "refunded"}:
            # The node knows the verdict: the escrow settled through another
            # path. Adopt it rather than marking a settled escrow 'failed'.
            self._adopt_escrow_verdict(session, job, payment, meta, escrow, now)
            logger.info(
                "Escrow settlement for job %s payment %s deferred %.0fs past bound; "
                "escrow read reports %s -- adopting the verdict",
                job.id,
                payment.id,
                elapsed,
                escrow["state"],
            )
            return True
        logger.error(
            "Escrow settlement for job %s payment %s deferred %.0fs past the %ss bound (%s); escrow %s -- still deferring",
            job.id,
            payment.id,
            elapsed,
            self.settle_max_seconds,
            outcome,
            f"read failed ({read_error}); cannot confirm absent"
            if read_error is not None
            else f"still present (state={escrow.get('state') if escrow else 'unreadable'})",
        )
        return False

    def _adopt_escrow_verdict(
        self,
        session: AsyncSession,
        job: MarketJob,
        payment: MarketJobPayment,
        meta: dict[str, Any],
        escrow: dict[str, Any],
        now: datetime,
    ) -> None:
        """Write the escrow row's own verdict onto job and payment."""
        meta.pop(META_SETTLE_DEFERRAL_FIRST_AT, None)
        payment.meta_data = meta
        if escrow["state"] == "released":
            job.state = "RELEASED"
            job.payment_status = "released"
            job.tx_hash = job.tx_hash or escrow.get("release_tx_hash")
            payment.status = "released"
            payment.transaction_hash = payment.transaction_hash or escrow.get("release_tx_hash")
            payment.released_at = payment.released_at or now
        else:
            job.state = "REFUNDED"
            job.payment_status = "refunded"
            job.refund_tx_hash = job.refund_tx_hash or escrow.get("refund_tx_hash")
            payment.status = "refunded"
            payment.refund_transaction_hash = payment.refund_transaction_hash or escrow.get("refund_tx_hash")
            payment.refunded_at = payment.refunded_at or now
        job.updated_at = now
        payment.updated_at = now
        session.add(job)
        session.add(payment)
