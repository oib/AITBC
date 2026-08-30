"""Release escrow once a customer's acceptance window has expired (G3).

Holding a payment for review only works if something eventually ends the hold. A
customer who never comes back must not be able to keep a provider's earnings locked
by doing nothing, so this loop settles every held payment whose deadline has passed.

Unlike the settlement reconciler this is not opt-in. The reconciler re-drives
payouts that were supposed to have happened already, which is a decision an operator
makes per deployment; this one performs the release the acceptance window deferred.
Without it, enabling a window would simply stop paying providers.

It runs whenever a window is configured, and stands down when
COORDINATOR_ACCEPTANCE_WINDOW_SECONDS is 0, because nothing can enter the held state
then.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from collections.abc import Callable

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc_shared import JobPayment

from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from ..acceptance import DISPUTED, PENDING_ACCEPTANCE, deadline_passed, default_window_seconds

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def sweeper_enabled() -> bool:
    """Whether the sweeper should run: only when an acceptance window is configured."""
    if os.getenv("COORDINATOR_ACCEPTANCE_SWEEP_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    return default_window_seconds() > 0


class AcceptanceSweeper:
    """Settle held payments whose acceptance window has run out."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_ACCEPTANCE_SWEEP_INTERVAL_SECONDS", 60)
        self.batch_size = batch_size or _env_int("COORDINATOR_ACCEPTANCE_SWEEP_BATCH_SIZE", 50)
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _find_held(self, session: Any) -> list[Job]:
        """Jobs whose payment is waiting on the customer.

        Disputed payments are deliberately excluded: a rejection is a request for an
        operator to rule, and sweeping it to the provider on a timer would make the
        dispute path decorative.
        """
        stmt = (
            select(Job)
            .join(JobPayment, Job.payment_id == JobPayment.id)
            .where(JobPayment.status == PENDING_ACCEPTANCE)
            .limit(self.batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    async def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        from .payments import PaymentService

        counts = {"held": 0, "expired": 0, "released": 0, "failed": 0}
        with self._session_factory() as session:
            for job in self._find_held(session):
                counts["held"] += 1
                if not job.payment_id:
                    continue
                payment = session.get(JobPayment, job.payment_id)
                if payment is None or payment.status == DISPUTED:
                    continue
                if not deadline_passed(payment.meta_data):
                    continue
                counts["expired"] += 1
                try:
                    released = await PaymentService(session).release_payment(
                        job.client_id, job.id, job.payment_id, reason="Acceptance window expired"
                    )
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("Acceptance sweep raised for job %s: %s", job.id, e)
                    continue
                if released:
                    job.payment_status = "released"
                    session.add(job)
                    session.commit()
                    counts["released"] += 1
                    logger.info("Acceptance window expired for job %s; released payment %s", job.id, job.payment_id)
                else:
                    # Left held rather than marked released: the escrow is still funded,
                    # and the next sweep retries it.
                    counts["failed"] += 1
                    logger.warning("Job %s did not settle after its acceptance window; retrying next sweep", job.id)
        logger.debug(
            "Acceptance sweep complete: held=%s expired=%s released=%s failed=%s",
            counts["held"],
            counts["expired"],
            counts["released"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "Acceptance window sweeper started: window=%ss interval=%ss batch=%s",
            default_window_seconds(),
            self.interval_seconds,
            self.batch_size,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                counts = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Acceptance sweep failed: %s", e)
                continue
            if counts["expired"]:
                logger.info(
                    "Acceptance sweep: expired=%s released=%s failed=%s",
                    counts["expired"],
                    counts["released"],
                    counts["failed"],
                )
