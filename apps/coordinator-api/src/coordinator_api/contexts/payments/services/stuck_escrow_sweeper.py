"""Auto-refund escrows that are stuck in non-completable job states.

A job that is canceled, fails, expires, or is disputed and never resolved may
still have its payment escrowed. This sweeper refunds those held payments back
to the buyer after a grace period, so funds do not remain locked forever.
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
from ..acceptance import DISPUTED, HELD_STATES, META_DISPUTED_AT
from .payments import PaymentService

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def stuck_escrow_sweeper_enabled() -> bool:
    """Whether the stuck-escrow sweeper should run. Defaults to true."""
    return os.getenv("COORDINATOR_STUCK_ESCROW_SWEEP_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _to_utc(dt: datetime | None) -> datetime | None:
    """Make a datetime comparable with ``datetime.now(UTC)``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _disputed_at(meta_data: dict[str, Any] | None) -> datetime | None:
    """Parse the disputed-at timestamp from payment metadata, if present."""
    if not meta_data:
        return None
    raw = meta_data.get(META_DISPUTED_AT)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError) as e:
        logger.warning("Could not parse disputed_at %r: %s", raw, e)
        return None


class StuckEscrowSweeper:
    """Refund held escrows for jobs that cannot complete or are not resolved."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        min_age_seconds: int | None = None,
        disputed_min_age_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_STUCK_ESCROW_SWEEP_INTERVAL_SECONDS", 300)
        # Give the normal cancel/fail/expire handlers time to settle on their own.
        self.min_age_seconds = min_age_seconds or _env_int("COORDINATOR_STUCK_ESCROW_SWEEP_MIN_AGE_SECONDS", 120)
        # Disputes are operator-resolvable; give them a longer default before auto-refunding.
        self.disputed_min_age_seconds = disputed_min_age_seconds or _env_int(
            "COORDINATOR_STUCK_ESCROW_SWEEP_DISPUTED_MIN_AGE_SECONDS", 86400
        )
        self.batch_size = batch_size or _env_int("COORDINATOR_STUCK_ESCROW_SWEEP_BATCH_SIZE", 25)
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _is_stuck(self, job: Job, payment: JobPayment) -> tuple[bool, str]:
        """Return (True, reason) if this held payment should be auto-refunded."""
        now = datetime.now(UTC)

        # Terminal non-completable job states.
        if job.state in {"CANCELED", "FAILED", "EXPIRED"}:
            updated_at = _to_utc(payment.updated_at)
            if updated_at and updated_at < now - timedelta(seconds=self.min_age_seconds):
                return True, f"job {job.state.lower()} and escrow not released"
            return False, ""

        # Disputed payments stay in held state until an operator rules. If no
        # ruling is issued within the longer grace period, refund the buyer.
        if job.payment_status == DISPUTED:
            disputed_at = _to_utc(_disputed_at(payment.meta_data)) or _to_utc(payment.updated_at)
            if disputed_at and disputed_at < now - timedelta(seconds=self.disputed_min_age_seconds):
                return True, "dispute not resolved and escrow not released"
            return False, ""

        return False, ""

    def _find_candidates(self, session: Any) -> list[tuple[Job, JobPayment, str]]:
        """Jobs whose payment is held but the job is canceled, failed, expired, or disputed."""
        stmt = (
            select(Job)
            .where(Job.payment_status.in_(HELD_STATES))  # type: ignore[union-attr]
            .where(Job.payment_id.is_not(None))  # type: ignore[union-attr]
            .where(Job.state.in_({"CANCELED", "FAILED", "EXPIRED"}))  # type: ignore[union-attr]
            .limit(self.batch_size)
        )
        jobs = list(session.execute(stmt).scalars().all())

        # Disputed payments may keep state==COMPLETED, so query them separately.
        dispute_stmt = (
            select(Job)
            .where(Job.payment_status == DISPUTED)
            .where(Job.payment_id.is_not(None))  # type: ignore[union-attr]
            .limit(self.batch_size)
        )
        jobs.extend(session.execute(dispute_stmt).scalars().all())

        out = []
        for job in jobs:
            payment = session.get(JobPayment, job.payment_id)
            if payment is None:
                continue
            should_refund, reason = self._is_stuck(job, payment)
            if should_refund:
                out.append((job, payment, reason))
        return out

    async def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        counts = {"candidates": 0, "refunded": 0, "failed": 0}
        with self._session_factory() as session:
            for job, _payment, reason in self._find_candidates(session):
                counts["candidates"] += 1
                if not job.payment_id:
                    continue
                try:
                    refunded = await PaymentService(session).refund_payment(job.client_id, job.id, job.payment_id, reason)
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Stuck escrow sweep raised for job %s: %s", job.id, e)
                    continue
                if refunded:
                    job.payment_status = "refunded"
                    session.add(job)
                    session.commit()
                    counts["refunded"] += 1
                    logger.info("Refunded stuck payment %s for job %s: %s", job.payment_id, job.id, reason)
                else:
                    counts["failed"] += 1
                    logger.warning("Job %s stuck escrow did not settle; retrying next sweep", job.id)
        logger.debug(
            "Stuck escrow sweep complete: candidates=%s refunded=%s failed=%s",
            counts["candidates"],
            counts["refunded"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "Stuck escrow sweeper started: interval=%ss min_age=%ss disputed_min_age=%ss batch=%s",
            self.interval_seconds,
            self.min_age_seconds,
            self.disputed_min_age_seconds,
            self.batch_size,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                counts = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Stuck escrow sweep failed: %s", e)
                continue
            if counts["candidates"]:
                logger.info(
                    "Stuck escrow sweep: candidates=%s refunded=%s failed=%s",
                    counts["candidates"],
                    counts["refunded"],
                    counts["failed"],
                )
