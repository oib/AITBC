"""Retry escrow releases whose on-chain settlement never landed.

A job can complete, have its payment escrowed, and still fail to settle: the chain
RPC may be briefly unreachable, or the settlement key misconfigured. Since release
now reports an unsettled payout instead of claiming success, such a payment stays
`escrowed` -- correct, but nothing retries it, so the provider's earnings sit in
`pending` indefinitely.

Retrying is only safe because settlement is idempotent. The ESCROW_RELEASE
transaction is deterministic, so a duplicate submitted at the same nonce is
deduplicated by the mempool, and the chain-side lookup short-circuits a job that
already settled. Without those two properties this loop would risk paying twice.

Disabled by default; set ESCROW_RECONCILER_ENABLED=true to run it.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from collections.abc import Callable

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ....storage.db import get_engine
from ...infrastructure.domain.job import Job

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def reconciler_enabled() -> bool:
    """Whether the reconciler should run. Off unless explicitly enabled."""
    return os.getenv("ESCROW_RECONCILER_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


class SettlementReconciler:
    """Re-attempt escrow releases for completed jobs that never settled on-chain."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        min_age_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("ESCROW_RECONCILER_INTERVAL_SECONDS", 300)
        # Give the normal completion path time to settle before treating a job as stuck.
        self.min_age_seconds = min_age_seconds or _env_int("ESCROW_RECONCILER_MIN_AGE_SECONDS", 120)
        self.batch_size = batch_size or _env_int("ESCROW_RECONCILER_BATCH_SIZE", 25)
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _find_unsettled(self, session: Any) -> list[Job]:
        """Completed jobs whose payment is still escrowed past the grace period."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)
        stmt = (
            select(Job)
            .where(Job.payment_status == "escrowed")
            .where(Job.completed_at.is_not(None))  # type: ignore[union-attr]
            .where(Job.completed_at < cutoff)  # type: ignore[operator]
            .limit(self.batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    async def run_once(self) -> dict[str, int]:
        """One reconciliation pass. Returns counts for logging and tests."""
        from .payments import PaymentService

        counts = {"retried": 0, "settled": 0, "failed": 0}
        scanned = 0
        with self._session_factory() as session:
            candidates = self._find_unsettled(session)
            scanned = len(candidates)
            for job in candidates:
                if not job.payment_id:
                    continue
                counts["retried"] += 1
                try:
                    settled = await PaymentService(session).release_payment(
                        job.client_id, job.id, job.payment_id, reason="Settlement reconciliation retry"
                    )
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Reconciliation raised for job %s: %s", job.id, e)
                    continue
                if settled:
                    job.payment_status = "released"
                    session.add(job)
                    session.commit()
                    counts["settled"] += 1
                    logger.info("Reconciled escrow settlement for job %s", job.id)
                else:
                    counts["failed"] += 1
                    logger.warning("Job %s still unsettled after retry; leaving it escrowed", job.id)
        # Heartbeat. A pass with nothing to do logs nothing else, so at info level
        # "ran clean" and "the task died" are indistinguishable. Debug so a normal
        # deployment stays quiet but an operator can prove the loop is alive.
        logger.debug(
            "Settlement reconciliation pass complete: scanned=%s retried=%s settled=%s failed=%s",
            scanned,
            counts["retried"],
            counts["settled"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "Escrow settlement reconciler started: interval=%ss min_age=%ss batch=%s",
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
                logger.error("Settlement reconciliation pass failed: %s", e)
                continue
            if counts["retried"]:
                logger.info(
                    "Settlement reconciliation: retried=%s settled=%s failed=%s",
                    counts["retried"],
                    counts["settled"],
                    counts["failed"],
                )
