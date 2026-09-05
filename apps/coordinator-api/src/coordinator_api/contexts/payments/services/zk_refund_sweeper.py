"""Auto-refund escrows whose ZK receipt proof failed (P2.1).

A job that completes but cannot produce a verified, correct ZK receipt will
never be releasable by `release_payment()`. Without an automatic refund path,
the customer's funds stay locked in `payment_status=escrowed` or loop forever
in `pending_acceptance` while the acceptance sweeper repeatedly tries and fails
to release them.

This loop identifies completed jobs for which ZK was required and the stored
receipt shows an unverifiable or incorrect computation, then refunds the escrow
back to the buyer.

Hardening notes:
- The query gates on ``JobPayment.escrowed_at`` so a payment that was never
  backed by an on-chain ESCROW_LOCK is not passed to ``refund_payment``.
- It also excludes any payment that already has a ``refund_transaction_hash``
  or whose ``PaymentEscrow`` is already marked refunded, closing the dedupe gap
  if two sweep paths run concurrently.
- After ``PaymentService.refund_payment`` returns, the sweeper checks the
  payment row for the authoritative on-chain hash. A refund is only final when
  the row carries that hash; an unbacked escrow that PaymentService marked as
  refunded-without-hash is downgraded to ``failed`` so it does not show up as a
  live refund in audits.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, col, select

from aitbc.aitbc_logging import get_logger
from aitbc_shared import JobPayment, PaymentEscrow

from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from ..acceptance import PENDING_ACCEPTANCE, SETTLEMENT_FAILED, deadline_from
from .payments import PaymentService, _computation_is_correct, _zk_required_for_payment, get_receipt_of_record

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


def _zk_receipt_is_valid(receipt: dict[str, Any] | None, job: Job | None = None) -> bool:
    """Return True only when the stored receipt proves a correct computation."""
    return _computation_is_correct(receipt, job)


def _get_canonical_receipt(session: Any, job: Job) -> dict[str, Any] | None:
    """Return the authoritative receipt for a job, preferring JobReceipt over Job.receipt."""
    return get_receipt_of_record(session, job)


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
        """Completed jobs whose ZK receipt failed and whose refund is not on-chain.

        A row is a candidate when:
        - the job is completed and old enough;
        - the payment was actually escrowed (``escrowed_at`` is set);
        - the payment is still in a held/refundable state, or it is already marked
          ``refunded`` locally but has no authoritative on-chain hash (stale residue).
        The authoritative dedupe gate is ``refund_transaction_hash``: once that field
        is set, the refund is considered final and is never retried.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)
        stmt = (
            select(Job, JobPayment)
            .join(JobPayment, col(Job.payment_id) == JobPayment.id)
            .where(col(Job.state) == "COMPLETED")
            .where(
                (col(JobPayment.status).in_({"escrowed", PENDING_ACCEPTANCE, SETTLEMENT_FAILED}))
                | ((col(JobPayment.status) == "refunded") & (col(JobPayment.refund_transaction_hash).is_(None)))
            )
            .where(col(JobPayment.escrowed_at).is_not(None))
            .where(col(JobPayment.refund_transaction_hash).is_(None))
            .where(col(Job.completed_at).is_not(None))
            .where(col(Job.completed_at) < cutoff)
            .limit(self.batch_size)
        )
        rows = list(session.execute(stmt).all())
        out = []
        for job, payment in rows:
            if not job.payment_id:
                continue
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
            receipt = _get_canonical_receipt(session, job)
            if _zk_receipt_is_valid(receipt, job):
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
                receipt = _get_canonical_receipt(session, job)
                reason = "ZK proof verification failed"
                if receipt and receipt.get("zk_status"):
                    reason = f"ZK proof verification failed (zk_status={receipt['zk_status']})"
                try:
                    refunded = await PaymentService(session).refund_payment(job.client_id, job.id, job.payment_id, reason)
                except Exception as e:
                    counts["failed"] += 1
                    logger.error("ZK refund sweep raised for job %s: %s", job.id, e)
                    continue
                if refunded:
                    # PaymentService commits its own changes. Reload to enforce the
                    # on-chain record invariant: a refund is only final when the
                    # payment row carries the authoritative on-chain tx hash.
                    payment = session.get(JobPayment, job.payment_id)
                    escrow = session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == job.payment_id)).first()
                    if payment and payment.status == "refunded" and payment.refund_transaction_hash:
                        job.payment_status = "refunded"
                        session.add(job)
                        session.commit()
                        counts["refunded"] += 1
                        logger.info("Refunded payment %s for job %s due to failed ZK receipt", job.payment_id, job.id)
                    else:
                        # PaymentService returned success but left no on-chain hash.
                        # This is an unbacked escrow or a submission that did not settle.
                        # Treat as failed so the ledger does not show a refund without proof.
                        counts["failed"] += 1
                        logger.warning(
                            "Job %s ZK refund returned no on-chain record (refund_transaction_hash=%s); treating as failed",
                            job.id,
                            getattr(payment, "refund_transaction_hash", None),
                        )
                        if payment:
                            payment.status = "failed"
                            payment.refunded_at = None
                            payment.updated_at = datetime.now(UTC)
                            session.add(payment)
                        job.payment_status = "failed"
                        session.add(job)
                        if escrow:
                            escrow.is_refunded = False
                            escrow.is_active = False
                            escrow.refunded_at = None
                            session.add(escrow)
                        session.commit()
                else:
                    counts["failed"] += 1
                    # PaymentService refused the refund. If the row is already marked
                    # ``refunded`` locally but has no on-chain record, it is stale
                    # residue that can never be valid; downgrade it to ``failed`` so
                    # the sweeper stops retrying and the ledger is not stuck.
                    payment = session.get(JobPayment, job.payment_id)
                    escrow = session.exec(select(PaymentEscrow).where(PaymentEscrow.payment_id == job.payment_id)).first()
                    if payment and payment.status == "refunded" and not payment.refund_transaction_hash:
                        logger.warning(
                            "Job %s ZK refund is marked refunded but has no on-chain record; downgrading to failed",
                            job.id,
                        )
                        payment.status = "failed"
                        payment.refunded_at = None
                        payment.updated_at = datetime.now(UTC)
                        session.add(payment)
                        job.payment_status = "failed"
                        session.add(job)
                        if escrow:
                            escrow.is_refunded = False
                            escrow.is_active = False
                            escrow.refunded_at = None
                            session.add(escrow)
                        session.commit()
                    else:
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
