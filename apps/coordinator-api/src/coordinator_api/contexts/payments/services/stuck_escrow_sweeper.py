"""Auto-refund escrows that are stuck in non-completable job states.

A job that is canceled, fails, expires, or is disputed and never resolved may
still have its payment escrowed. This sweeper refunds those held payments back
to the buyer after a grace period, so funds do not remain locked forever.

A refund the node defers with HTTP 425 ("escrow lock not yet sealed") is
retried, but only for a bounded time: a lock that never lands would get that
answer forever. Past the give-up window the sweeper asks the node where the
lock is and marks the payment failed (no refund, no chain write) only when the
lock is neither sealed nor in the mempool.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, col, select

from aitbc.aitbc_logging import get_logger
from aitbc.network import AsyncAITBCHTTPClient
from aitbc_shared import JobPayment, PaymentEscrow

from ....config import settings
from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from ..acceptance import DISPUTED, HELD_STATES, META_DISPUTED_AT, REFUNDABLE_STATES, SETTLEMENT_FAILED
from .payments import PaymentService, _find_http_status_error, _lookup_chain_lock

logger = get_logger(__name__)

# First time the node answered 425 "lock not sealed" to this payment's refund.
META_UNSEALED_SINCE = "unsealed_since"
META_REFUND_SKIPPED = "refund_skipped"
REFUND_SKIPPED_NEVER_SEALED = "escrow_lock_never_sealed"

# How many pending transactions the mempool probe asks for. A full page means
# the lock could sit beyond it, so the probe cannot call the lock absent.
_MEMPOOL_PROBE_LIMIT = 1000

LOCK_SEALED = "sealed"
LOCK_IN_MEMPOOL = "mempool"
LOCK_ABSENT = "absent"


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


def _parse_utc(raw: Any) -> datetime | None:
    """Parse an ISO timestamp from payment metadata as UTC, or None."""
    if not raw:
        return None
    try:
        return _to_utc(datetime.fromisoformat(str(raw)))
    except (TypeError, ValueError):
        return None


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
        unsealed_giveup_seconds: int | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_STUCK_ESCROW_SWEEP_INTERVAL_SECONDS", 300)
        # Give the normal cancel/fail/expire handlers time to settle on their own.
        self.min_age_seconds = min_age_seconds or _env_int("COORDINATOR_STUCK_ESCROW_SWEEP_MIN_AGE_SECONDS", 120)
        # Disputes are operator-resolvable; give them a longer default before auto-refunding.
        self.disputed_min_age_seconds = disputed_min_age_seconds or _env_int(
            "COORDINATOR_STUCK_ESCROW_SWEEP_DISPUTED_MIN_AGE_SECONDS", 86400
        )
        self.batch_size = batch_size or _env_int("COORDINATOR_STUCK_ESCROW_SWEEP_BATCH_SIZE", 25)
        # How long a refund may keep getting 425 "lock not sealed" before the
        # sweeper checks whether the lock exists at all.
        self.unsealed_giveup_seconds = unsealed_giveup_seconds or _env_int(
            "COORDINATOR_STUCK_ESCROW_UNSEALED_GIVEUP_SECONDS", 3600
        )
        self.dry_run = os.getenv("COORDINATOR_STUCK_ESCROW_SWEEP_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")
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
        if payment.status == DISPUTED:
            disputed_at = _to_utc(_disputed_at(payment.meta_data)) or _to_utc(payment.updated_at)
            if disputed_at and disputed_at < now - timedelta(seconds=self.disputed_min_age_seconds):
                return True, "dispute not resolved and escrow not released"
            return False, ""

        return False, ""

    def _find_candidates(self, session: Any) -> list[tuple[Job, JobPayment, str]]:
        """Jobs whose payment is held but the job is canceled, failed, expired, or disputed."""
        stmt = (
            select(Job, JobPayment)
            .join(JobPayment, col(Job.payment_id) == JobPayment.id)
            .where(col(JobPayment.status).in_(HELD_STATES | {SETTLEMENT_FAILED}))
            .where(col(JobPayment.escrowed_at).is_not(None))
            .where(col(Job.payment_id).is_not(None))
            .where(col(Job.state).in_({"CANCELED", "FAILED", "EXPIRED"}))
            .limit(self.batch_size)
        )
        jobs = list(session.execute(stmt).all())

        # Disputed payments may keep state==COMPLETED, so query them separately.
        dispute_stmt = (
            select(Job, JobPayment)
            .join(JobPayment, col(Job.payment_id) == JobPayment.id)
            .where(JobPayment.status == DISPUTED)
            .where(col(JobPayment.escrowed_at).is_not(None))
            .where(col(Job.payment_id).is_not(None))
            .where(col(Job.state) == "COMPLETED")
            .limit(self.batch_size)
        )
        jobs.extend(session.execute(dispute_stmt).all())

        out = []
        for job, payment in jobs:
            if payment is None:
                continue
            should_refund, reason = self._is_stuck(job, payment)
            if should_refund:
                out.append((job, payment, reason))
        return out

    async def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        counts = {"candidates": 0, "refunded": 0, "failed": 0, "deferred": 0, "demoted": 0}
        with self._session_factory() as session:
            for job, _payment, reason in self._find_candidates(session):
                counts["candidates"] += 1
                if not job.payment_id:
                    continue
                if self.dry_run:
                    logger.info(
                        "[DRY-RUN] Would refund stuck payment %s for job %s: %s",
                        job.payment_id,
                        job.id,
                        reason,
                    )
                    counts["refunded"] += 1
                    continue
                try:
                    refunded = await PaymentService(session).refund_payment(
                        job.client_id, job.id, job.payment_id, reason, is_admin=True
                    )
                except Exception as e:
                    status_error = _find_http_status_error(e)
                    if status_error is not None and status_error.response.status_code == 425:
                        counts[await self._handle_unsealed_lock(session, job, _payment.id)] += 1
                        continue
                    counts["failed"] += 1
                    logger.error("Stuck escrow sweep raised for job %s: %s", job.id, e)
                    continue
                if refunded:
                    counts[self._apply_refunded_result(session, job, _payment.id, reason)] += 1
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

    def _apply_refunded_result(self, session: Any, job: Job, payment_row_id: str, reason: str) -> str:
        """Apply the row writes for a refund the service reported done.

        A refund the chain never recorded (no refund_transaction_hash) is
        downgraded to failed rather than left claiming refunded. Returns the
        counts key: "refunded" or "failed"."""
        now = datetime.now(UTC)
        payment = session.get(JobPayment, payment_row_id)
        escrow = (
            (session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).scalars().first())
            if payment
            else None
        )
        if payment and payment.status == "refunded" and payment.refund_transaction_hash:
            payment.refunded_at = now
            payment.updated_at = now
            session.add(payment)
            job.payment_status = "refunded"
            session.add(job)
            if escrow:
                escrow.is_refunded = True
                escrow.is_active = False
                escrow.refunded_at = now
                session.add(escrow)
            session.commit()
            logger.info("Refunded stuck payment %s for job %s: %s", payment.id, job.id, reason)
            return "refunded"
        if payment and payment.status == "refunded":
            logger.warning(
                "Job %s stuck escrow refund has no on-chain record; downgrading to failed",
                job.id,
            )
            payment.status = "failed"
            payment.refunded_at = None
            payment.updated_at = now
            session.add(payment)
            job.payment_status = "failed"
            session.add(job)
            if escrow:
                escrow.is_refunded = False
                escrow.is_active = False
                escrow.refunded_at = None
                session.add(escrow)
            session.commit()
            return "failed"
        logger.warning("Job %s stuck escrow did not settle; retrying next sweep", job.id)
        return "failed"

    async def _handle_unsealed_lock(self, session: Any, job: Job, payment_id: str) -> str:
        """Bound the wait on a refund the node defers with 425 "lock not sealed".

        The 425 means "not yet, retry" for a lock still in flight. The first one
        stamps the payment; inside the give-up window the refund is simply
        retried next sweep. Past the window the node is asked where the lock is,
        and the payment is demoted only when the lock is neither sealed nor in
        the mempool. An answer the sweeper cannot get keeps the payment held.
        Returns the counts key: "deferred" or "demoted".
        """
        payment = session.get(JobPayment, payment_id, populate_existing=True)
        if payment is None or payment.status not in REFUNDABLE_STATES:
            return "deferred"
        now = datetime.now(UTC)
        meta = dict(payment.meta_data or {})
        since = _parse_utc(meta.get(META_UNSEALED_SINCE))
        if since is None:
            meta[META_UNSEALED_SINCE] = now.isoformat()
            payment.meta_data = meta
            session.add(payment)
            session.commit()
            logger.warning(
                "Refund for job %s payment %s deferred: the escrow lock is not sealed; "
                "retrying each sweep and checking the lock after %ss",
                job.id,
                payment_id,
                self.unsealed_giveup_seconds,
            )
            return "deferred"
        waited = (now - since).total_seconds()
        if waited <= self.unsealed_giveup_seconds:
            logger.debug("Refund for job %s still deferred by 425 after %.0fs", job.id, waited)
            return "deferred"
        try:
            presence, lock_hash = await self._lock_presence(job.id)
        except Exception as e:
            logger.warning(
                "Could not tell where the escrow lock for job %s is; keeping payment %s held: %s",
                job.id,
                payment_id,
                e,
            )
            return "deferred"
        if presence != LOCK_ABSENT:
            logger.warning(
                "Escrow lock for job %s is %s after %.0fs of 425; keeping payment %s held",
                job.id,
                presence,
                waited,
                payment_id,
            )
            return "deferred"
        if not self._demote_never_sealed(session, job, payment_id, meta, now):
            return "deferred"
        logger.warning(
            "Escrow lock %s for job %s never sealed (425 for %.0fs, absent from blocks and mempool); "
            "payment %s marked failed with no refund: nothing was locked on chain",
            lock_hash or "(unknown hash)",
            job.id,
            waited,
            payment_id,
        )
        return "demoted"

    def _demote_never_sealed(self, session: Any, job: Job, payment_id: str, meta: dict[str, Any], now: datetime) -> bool:
        """Mark the payment failed, but only while it is still held.

        Two workers may reach the same payment in one sweep; the conditional
        update lets exactly one of them demote it and the other do nothing.
        """
        meta = dict(meta)
        meta[META_REFUND_SKIPPED] = REFUND_SKIPPED_NEVER_SEALED
        result = session.execute(
            update(JobPayment)
            .where(col(JobPayment.id) == payment_id)
            .where(col(JobPayment.status).in_(REFUNDABLE_STATES))
            .values(status="failed", meta_data=meta, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            session.rollback()
            logger.debug("Payment %s left the held states before the demotion; nothing to do", payment_id)
            return False
        job.payment_status = "failed"
        session.add(job)
        escrow = session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
        if escrow:
            escrow.is_active = False
            escrow.is_refunded = False
            session.add(escrow)
        session.commit()
        return True

    async def _lock_presence(self, job_id: str) -> tuple[str, str | None]:
        """Where the node holds the job's ESCROW_LOCK, and the lock hash it records.

        Returns ("sealed" | "mempool" | "absent", hash or None). Raises when
        the node cannot answer, so "could not tell" is never read as "absent".
        """
        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AsyncAITBCHTTPClient(timeout=10.0, api_key=settings.blockchain_rpc_api_key)
        if await _lookup_chain_lock(rpc_url, client, job_id):
            return LOCK_SEALED, None
        # No chain_id: the node then reads its own chain, the one the lock was
        # submitted to; a mismatched id would filter everything out and read
        # as "absent". The route has no job filter and no tx hash per entry.
        pending = await client.get_json(f"{rpc_url}/rpc/mempool?limit={_MEMPOOL_PROBE_LIMIT}")
        if (
            not isinstance(pending, dict)
            or pending.get("success") is False
            or pending.get("error")
            or not isinstance(pending.get("transactions"), list)
        ):
            raise RuntimeError(f"unusable mempool answer for job {job_id}")
        txs = pending["transactions"]
        if len(txs) >= _MEMPOOL_PROBE_LIMIT:
            raise RuntimeError(f"mempool page full ({len(txs)} txs); cannot rule the lock out")
        # Any pending transaction naming the job keeps it held, not only the lock.
        if any(isinstance(tx, dict) and (tx.get("payload") or {}).get("job_id") == job_id for tx in txs):
            return LOCK_IN_MEMPOOL, None
        # The node's escrow row only names the hash for the log; it is not evidence.
        lock_hash = None
        try:
            record = await client.get_json(f"{rpc_url}/rpc/escrow/{job_id}")
            if isinstance(record, dict) and record.get("lock_tx_hash"):
                lock_hash = str(record["lock_tx_hash"])
        except Exception as e:
            logger.debug("No escrow record hash for job %s: %s", job_id, e)
        return LOCK_ABSENT, lock_hash

    async def run_forever(self) -> None:
        logger.info(
            "Stuck escrow sweeper started: interval=%ss min_age=%ss disputed_min_age=%ss batch=%s dry_run=%s",
            self.interval_seconds,
            self.min_age_seconds,
            self.disputed_min_age_seconds,
            self.batch_size,
            self.dry_run,
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
                    "Stuck escrow sweep: candidates=%s refunded=%s failed=%s deferred=%s demoted=%s",
                    counts["candidates"],
                    counts["refunded"],
                    counts["failed"],
                    counts["deferred"],
                    counts["demoted"],
                )
