"""Park escrows whose ZK receipt proof failed for operator review (#3079).

A job that completes but cannot produce a verified, correct ZK receipt can
never be released by ``release_payment()`` while the gate is active. Every
such candidate is *delivered work* — the job is COMPLETED, so the provider
already ran it — which means an automatic refund here pays the buyer for
work the provider delivered and leaves the provider unpaid (the #3067
forensics: two 15-AIT provider payouts lost to exactly this path).

The gate is also architecturally circular: the only circuit is a toy, the
proof binds nothing job-specific, and the coordinator is prover, verifier
and judge over its own database. Until the gate is rebuilt on real
commitments, a gate failure is platform incoherence, not evidence the buyer
deserves a refund — so this loop no longer moves money at all. It marks the
payment ``settlement_failed`` (the documented "an operator has to reset it —
or refund it — deliberately" state), which takes the escrow out of every
release and refund sweeper's candidate set while keeping it refundable by an
operator through the admin dispute/refund paths.

What changed vs. the old auto-refund sweeper:
- ``PaymentService.refund_payment`` is never called here. Gate-failed
  escrows are parked, not refunded.
- ``settlement_failed`` rows are no longer candidates — they are already
  parked. Stale ``refunded``-without-hash residue is likewise out of scope;
  the settlement reconciler's refund-hash audit (#3007) owns that cleanup.
- Disputed payments stay with the dispute flow, as before.

Multi-worker safety is unchanged: each pass runs under a ``filelock``
(``COORDINATOR_ZK_REFUND_SWEEP_LOCK_PATH``, default
``/var/lib/aitbc/zk_refund_sweeper.lock``). A worker that loses the race
skips the pass; a missing/unwritable lock file degrades to the pre-lock
behaviour with a warning.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import InvalidOperation
from typing import Any

import filelock
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select, update

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError
from aitbc_shared import JobPayment

from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from ..acceptance import PENDING_ACCEPTANCE, SETTLEMENT_FAILED, deadline_from
from .payments import _computation_is_correct, _zk_required_for_payment, get_receipt_of_record

logger = get_logger(__name__)

# Expected failure surface for the ZK escrow sweep — it writes payment rows,
# a money-adjacent path, so the tuple mirrors the payment service's own
# surface: filesystem/JSON, data-shape, runtime, SQLAlchemy session errors,
# lazy imports, filelock errors, the aitbc error hierarchy, HTTPException,
# decimal parse failures, timestamp overflows and assertion guards.
# BaseExceptions still propagate (asyncio.CancelledError is re-raised
# explicitly).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    IndexError,
    TypeError,
    AttributeError,
    RuntimeError,
    AssertionError,
    OverflowError,
    ImportError,
    SQLAlchemyError,
    AITBCError,
    InvalidOperation,
    HTTPException,
)

# Payment meta markers stamped when the sweep parks a gate-failed escrow.
# ``zk_gate_review`` is the operator-facing flag: the escrow is held, the job
# delivered, and only a deliberate admin action (retry-release after fixing
# the gate, or an admin refund) may move the money.
META_ZK_GATE_REVIEW = "zk_gate_review"
META_ZK_GATE_REVIEW_AT = "zk_gate_review_at"
META_ZK_GATE_REVIEW_STATUS = "zk_gate_review_status"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def zk_refund_sweeper_enabled() -> bool:
    """Whether the sweeper should run. Defaults to true so gate-failed escrows get parked, not stranded."""
    return os.getenv("COORDINATOR_ZK_REFUND_SWEEP_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _zk_receipt_is_valid(receipt: dict[str, Any] | None, job: Job | None = None) -> bool:
    """Return True only when the stored receipt proves a correct computation."""
    return _computation_is_correct(receipt, job)


def _get_canonical_receipt(session: Any, job: Job) -> dict[str, Any] | None:
    """Return the authoritative receipt for a job, preferring JobReceipt over Job.receipt."""
    return get_receipt_of_record(session, job)


class ZkRefundSweeper:
    """Park escrows for completed jobs whose ZK receipt proof did not verify.

    The class and ``COORDINATOR_ZK_REFUND_SWEEP_*`` env names are kept for
    operator compatibility; since #3079 the sweep parks for review instead
    of refunding — see the module docstring.
    """

    def __init__(
        self,
        interval_seconds: int | None = None,
        min_age_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
        lock_path: str | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_ZK_REFUND_SWEEP_INTERVAL_SECONDS", 60)
        # Give the normal completion path a grace period before sweeping in and
        # parking; a slow ZK proof generation should not be pre-empted.
        self.min_age_seconds = min_age_seconds or _env_int("COORDINATOR_ZK_REFUND_SWEEP_MIN_AGE_SECONDS", 120)
        self.batch_size = batch_size or _env_int("COORDINATOR_ZK_REFUND_SWEEP_BATCH_SIZE", 25)
        self._session_factory = session_factory or (lambda: Session(get_engine()))
        # Cross-process sweep lock. A real lock is what makes a second worker
        # harmless — it loses the race and skips the pass.
        self._sweep_lock = filelock.FileLock(
            lock_path or os.getenv("COORDINATOR_ZK_REFUND_SWEEP_LOCK_PATH") or "/var/lib/aitbc/zk_refund_sweeper.lock"
        )

    def _find_candidates(self, session: Any) -> list[tuple[Job, JobPayment]]:
        """Completed jobs whose ZK receipt failed and whose escrow is still held.

        A row is a candidate when:
        - the job is completed and old enough (delivered work — never
          auto-refunded, only parked for review);
        - the payment was actually escrowed (``escrowed_at`` is set);
        - the payment is still in a held state (``escrowed`` or
          ``pending_acceptance`` past its window). ``settlement_failed`` rows
          are already parked; ``disputed`` rows belong to the dispute flow;
          ``refunded`` rows are owned by the refund-hash audit (#3007).
        The authoritative dedupe gate is ``refund_transaction_hash``: once
        that field is set, the row is out of scope entirely.
        """
        # Job.completed_at is a naive-UTC column (SQLModel datetime maps to
        # DateTime without tz); bind a naive cutoff like the reapers do so
        # the comparison does not depend on dialect tz coercion (#1575).
        cutoff = (datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)).replace(tzinfo=None)
        stmt = (
            select(Job, JobPayment)
            .join(JobPayment, col(Job.payment_id) == JobPayment.id)
            .where(col(Job.state) == "COMPLETED")
            .where(col(JobPayment.status).in_({"escrowed", PENDING_ACCEPTANCE}))
            .where(col(JobPayment.escrowed_at).is_not(None))
            .where(col(JobPayment.refund_transaction_hash).is_(None))
            .where(col(Job.completed_at).is_not(None))
            .where(col(Job.completed_at) < cutoff)
        )
        # Page with OFFSET until a short page: the Python-side eligibility
        # filters below (acceptance window, ZK requirement, valid receipt)
        # would otherwise let a head of ineligible rows starve eligible ones
        # behind them (#2699).
        rows = []
        offset = 0
        while True:
            page = list(session.execute(stmt.order_by(Job.id).offset(offset).limit(self.batch_size)).all())
            rows.extend(page)
            if len(page) < self.batch_size:
                break
            offset += self.batch_size
        out = []
        for job, payment in rows:
            if not job.payment_id:
                continue
            if payment is None:
                continue
            # Respect an open acceptance window: if the customer is still within
            # the review window, do not pre-emptively park. The acceptance
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
        counts = {"candidates": 0, "parked": 0, "failed": 0, "skipped": 0}
        locked = False
        try:
            self._sweep_lock.acquire(timeout=0.05)  # noqa: unawaited-async — sync filelock.FileLock
            locked = True
        except filelock.Timeout:
            logger.debug("ZK escrow sweep skipped: another worker holds the sweep lock")
            counts["skipped"] = 1
            return counts
        except OSError as e:
            # The lock file's directory is missing or unwritable (tests, dev
            # machines). That was the pre-lock behaviour; refusing to sweep
            # would strand escrows where no second worker exists anyway.
            logger.warning("ZK escrow sweep lock unavailable (%s); sweeping unguarded", e)
        try:
            return await self._run_sweep(counts)
        finally:
            if locked:
                self._sweep_lock.release()  # noqa: unawaited-async — sync filelock.FileLock

    def _park_for_operator_review(self, session: Any, job: Job, payment: JobPayment) -> bool:
        """Move a gate-failed escrow to ``settlement_failed`` — held, not refunded.

        ``settlement_failed`` is the codebase's operator-review state: every
        release and refund sweeper's candidate set excludes it, the escrow
        stays locked on-chain, and an admin can still refund deliberately
        (``refund_payment`` accepts it via ``REFUNDABLE_STATES``) or re-arm
        the release path (``POST /admin/payments/{job_id}/retry-release``)
        once the gate is fixed.

        Returns True only when this call won the status CAS. The candidate
        read in ``_find_candidates`` is stale by commit time: another session
        can move the payment to disputed/refunded/released/failed — or merge
        ``meta_data`` (dispute_reason etc.) — in between, so the write is a
        conditional UPDATE in the #1797 ``_cas_payment_transition`` idiom
        (same shape as ``payments_release._release_attempts_exhausted``), not
        an ORM-object overwrite. Losing the CAS means the row already moved
        and the park must not clobber it.
        """
        receipt = _get_canonical_receipt(session, job)
        zk_status = (receipt or {}).get("zk_status") or "unknown"
        now = datetime.now(UTC)
        # Refresh before merging meta: bulk UPDATEs elsewhere leave the ORM
        # row stale, and a concurrent writer may have added meta keys the
        # park must preserve rather than erase.
        session.refresh(payment)  # sync Session (sqlmodel)
        meta = dict(payment.meta_data or {})
        meta[META_ZK_GATE_REVIEW] = True
        meta[META_ZK_GATE_REVIEW_AT] = now.isoformat()
        meta[META_ZK_GATE_REVIEW_STATUS] = str(zk_status)
        claim = session.execute(
            update(JobPayment)
            .where(col(JobPayment.id) == payment.id)
            .where(col(JobPayment.status).in_(("escrowed", PENDING_ACCEPTANCE)))
            .where(col(JobPayment.refund_transaction_hash).is_(None))
            .values(status=SETTLEMENT_FAILED, meta_data=meta, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if getattr(claim, "rowcount", 0) != 1:
            session.rollback()  # noqa: unawaited-async — sync Session (sqlmodel)
            logger.info(
                "Job %s ZK park skipped: payment %s already moved out of the held set",
                job.id,
                payment.id,
            )
            return False
        job.payment_status = SETTLEMENT_FAILED
        session.add(job)
        session.commit()  # sync Session (sqlmodel)
        logger.warning(
            "Job %s delivered work but its ZK gate failed (zk_status=%s); "
            "payment %s parked as settlement_failed for operator review — "
            "no automatic refund (#3079)",
            job.id,
            zk_status,
            payment.id,
        )
        return True

    async def _run_sweep(self, counts: dict[str, int]) -> dict[str, int]:
        with self._session_factory() as session:
            for job, payment in self._find_candidates(session):
                counts["candidates"] += 1
                if not job.payment_id:
                    continue
                try:
                    if self._park_for_operator_review(session, job, payment):
                        counts["parked"] += 1
                except _OPS_ERRORS as e:
                    counts["failed"] += 1
                    session.rollback()  # noqa: unawaited-async — sync Session (sqlmodel)
                    logger.error("ZK escrow sweep failed to park job %s: %s", job.id, e)
        logger.debug(
            "ZK escrow sweep complete: candidates=%s parked=%s failed=%s",
            counts["candidates"],
            counts["parked"],
            counts["failed"],
        )
        return counts

    async def run_forever(self) -> None:
        logger.info(
            "ZK escrow sweeper started (park-for-review, no auto-refund #3079): interval=%ss min_age=%ss batch=%s",
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
            except _OPS_ERRORS as e:
                logger.error("ZK escrow sweep failed: %s", e)
                continue
            if counts["candidates"]:
                logger.info(
                    "ZK escrow sweep: candidates=%s parked=%s failed=%s",
                    counts["candidates"],
                    counts["parked"],
                    counts["failed"],
                )
