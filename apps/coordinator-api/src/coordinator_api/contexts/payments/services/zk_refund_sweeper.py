"""Auto-refund escrows whose ZK receipt proof failed (P2.1).

A job that completes but cannot produce a verified, correct ZK receipt will
never be releasable by `release_payment()`. Without an automatic refund path,
the customer's funds stay locked in `payment_status=escrowed` or loop forever
in `pending_acceptance` while the acceptance sweeper repeatedly tries and fails
to release them.

This loop identifies completed jobs for which ZK was required and the stored
receipt shows an unverifiable or incorrect computation, then refunds the escrow
back to the buyer.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc_shared import JobPayment

from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from ..acceptance import PENDING_ACCEPTANCE, deadline_from
from .payments import PaymentService, _zk_required_for_payment

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def zk_refund_sweeper_enabled() -> bool:
    """Whether the sweeper should run. Defaults to true so failed ZK jobs do not strand funds."""
    return os.getenv("COORDINATOR_ZK_REFUND_SWEEP_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _zk_receipt_is_valid(receipt: dict[str, Any] | None) -> bool:
    """Return True only when the stored receipt proves a correct computation."""
    if not receipt:
        return False
    return receipt.get("zk_status") == "verified" and receipt.get("computation_correct") is True


class ZkRefundSweeper:
    """Refund escrows for completed jobs whose ZK receipt proof did not verify."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        min_age_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_ZK_REFUND_SWEEP_INTERVAL_SECONDS", 60)
        # Give the normal completion path a grace period before sweeping in and
        # refunding; a slow ZK proof generation should not be pre-empted.
        self.min_age_seconds = min_age_seconds or _env_int("COORDINATOR_ZK_REFUND_SWEEP_MIN_AGE_SECONDS", 120)
        self.batch_size = batch_size or _env_int("COORDINATOR_ZK_REFUND_SWEEP_BATCH_SIZE", 25)
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _find_candidates(self, session: Any) -> list[tuple[Job, JobPayment]]:
        """Completed jobs whose ZK receipt failed and whose escrow is still locked."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)
        stmt = (
            select(Job)
            .where(Job.state == "COMPLETED")
            .where(Job.payment_status.in_({"escrowed", PENDING_ACCEPTANCE}))  # type: ignore[union-attr]
            .where(Job.completed_at.is_not(None))  # type: ignore[union-attr]
            .where(Job.completed_at < cutoff)  # type: ignore[operator]
            .limit(self.batch_size)
        )
        jobs = list(session.execute(stmt).scalars().all())
        out = []
        for job in jobs:
            if not job.payment_id:
                continue
            payment = session.get(JobPayment, job.payment_id)
            if payment is None:
                continue
            # Respect an open acceptance window: if the customer is still within
            # the review window, do not pre-emptively refund. The acceptance
            # sweeper will try release on expiry and fail for ZK reasons; this
            # loop will then pick it up on the next pass.
            if payment.status == PENDING_ACCEPTANCE:
                deadline = deadline_from(payment.meta_data)
                if deadline and deadline > datetime.now(UTC):
                    continue
            if not _zk_required_for_payment(payment.amount, job):
                continue
            if _zk_receipt_is_valid(job.receipt):
                continue
            out.append((job, payment))
        return out

    async def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        counts = {"candidates": 0, "refunded": 0, "failed": 0}
        with self._session_factory() as session:
            for job, _payment in self._find_candidates(session):
                counts["candidates"] += 1
                if not job.payment_id:
                    continue
                reason = "ZK proof verification failed"
                if job.receipt and job.receipt.get("zk_status"):
                    reason = f"ZK proof verification failed (zk_status={job.receipt['zk_status']})"
                try:
                    refunded = await PaymentService(session).refund_payment(job.client_id, job.id, job.payment_id, reason)
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("ZK refund sweep raised for job %s: %s", job.id, e)
                    continue
                if refunded:
                    job.payment_status = "refunded"
                    session.add(job)
                    session.commit()
                    counts["refunded"] += 1
                    logger.info("Refunded payment %s for job %s due to failed ZK receipt", job.payment_id, job.id)
                else:
                    counts["failed"] += 1
                    logger.warning("Job %s ZK refund did not settle; retrying next sweep", job.id)
        logger.debug(
            "ZK refund sweep complete: candidates=%s refunded=%s failed=%s",
            counts["candidates"],
            counts["refunded"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "ZK refund sweeper started: interval=%ss min_age=%ss batch=%s",
            self.interval_seconds,
            self.min_age_seconds,
            self.batch_size,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                counts = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("ZK refund sweep failed: %s", e)
                continue
            if counts["candidates"]:
                logger.info(
                    "ZK refund sweep: candidates=%s refunded=%s failed=%s",
                    counts["candidates"],
                    counts["refunded"],
                    counts["failed"],
                )
