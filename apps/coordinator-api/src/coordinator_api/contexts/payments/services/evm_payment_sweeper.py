"""Re-verify EVM protected payments stuck in ``pending`` (#2818).

``PaymentService._verify_evm_receipt`` runs once, inline at payment
creation. When the EVM RPC is unconfigured, the receipt is not yet mined,
or the RPC call fails, the payment is left ``pending`` — and nothing ever
drives it again: ``StuckEscrowSweeper`` only sees payments with
``escrowed_at`` set, which an EVM payment never gets. The job then sits on
``payment_status='pending'`` forever even after the buyer's on-chain
rental transaction confirms.

This sweeper re-runs the same receipt verification for pending EVM
payments on an interval. A confirmed receipt flips the payment (and the
denormalized ``job.payment_status`` the dispatch gate reads) to
``confirmed``; a receipt that failed on-chain or fails the agreement
binding flips it to ``failed`` — the same outcomes the inline path
produces. Payments whose quote snapshot or RPC answer is unavailable stay
``pending`` for the next pass, exactly as they do today.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, col, select
from starlette.concurrency import run_in_threadpool

from aitbc.aitbc_logging import get_logger
from aitbc.market.energy_pricing import EnergyPricingError, EnergyQuote
from aitbc_shared import JobPayment

from ....schemas import JobPaymentCreate
from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from .payments import PaymentService
from .payments_helpers import _OPS_ERRORS

logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def evm_payment_sweeper_enabled() -> bool:
    """Whether the EVM payment re-verify sweeper should run. Defaults to true."""
    return os.getenv("COORDINATOR_EVM_PAYMENT_SWEEP_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _to_utc(dt: datetime | None) -> datetime | None:
    """Make a datetime comparable with ``datetime.now(UTC)``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _evm_tx_hash(payment: JobPayment) -> str | None:
    """The buyer-submitted EVM tx hash recorded at creation, if any."""
    meta = payment.meta_data or {}
    raw = meta.get("evm_tx_hash")
    return str(raw) if raw else None


def _rebuild_payment_data(payment: JobPayment, job: Job) -> JobPaymentCreate | None:
    """Reconstruct the create-time request fields receipt verification reads.

    ``_verify_evm_receipt`` only consults ``evm_tx_hash`` and
    ``evm_agreement_id``; ``evm_escrow_id`` rides along for parity with the
    recorded metadata. Returns None when the stored amount cannot satisfy
    the request schema (defensive — creation already validated it).
    """
    meta = payment.meta_data or {}
    try:
        return JobPaymentCreate(
            job_id=payment.job_id or job.id,
            amount=Decimal(str(payment.amount)),
            currency=payment.currency or "AITBC",
            payment_method=payment.payment_method or "evm",
            evm_tx_hash=_evm_tx_hash(payment),
            evm_agreement_id=meta.get("evm_agreement_id"),
            evm_escrow_id=meta.get("evm_escrow_id"),
        )
    except (ValueError, InvalidOperation, TypeError) as e:
        logger.warning("Cannot rebuild payment data for EVM payment %s: %s", payment.id, e)
        return None


def _rebuild_quote(job: Job) -> EnergyQuote | None:
    """Reconstruct the signed energy quote from the job's stored snapshot."""
    snapshot = job.energy_quote_snapshot
    if not snapshot:
        return None
    try:
        return EnergyQuote.from_dict(snapshot)
    except (TypeError, ValueError, EnergyPricingError, KeyError) as e:
        logger.warning("Cannot rebuild energy quote for job %s: %s", job.id, e)
        return None


class EvmPaymentVerifySweeper:
    """Re-drive receipt verification for pending EVM protected payments."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        min_age_seconds: int | None = None,
        batch_size: int | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("COORDINATOR_EVM_PAYMENT_SWEEP_INTERVAL_SECONDS", 60)
        # Give the inline verification and mempool propagation a moment first.
        self.min_age_seconds = min_age_seconds or _env_int("COORDINATOR_EVM_PAYMENT_SWEEP_MIN_AGE_SECONDS", 30)
        self.batch_size = batch_size or _env_int("COORDINATOR_EVM_PAYMENT_SWEEP_BATCH_SIZE", 25)
        self.dry_run = os.getenv("COORDINATOR_EVM_PAYMENT_SWEEP_DRY_RUN", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._session_factory = session_factory or (lambda: Session(get_engine()))

    def _find_candidates(self, session: Any) -> list[tuple[Job, JobPayment]]:
        """Pending EVM payments old enough to re-check, with their job row."""
        stmt = (
            select(JobPayment, Job)
            .join(Job, col(Job.payment_id) == JobPayment.id)
            .where(col(JobPayment.status) == "pending")
            .where(col(JobPayment.payment_method) == "evm")
            .where(col(JobPayment.escrowed_at).is_(None))
        )
        cutoff = datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)
        out: list[tuple[Job, JobPayment]] = []
        offset = 0
        while True:
            page = list(session.execute(stmt.order_by(JobPayment.id).offset(offset).limit(self.batch_size)).all())
            for payment, job in page:
                if _evm_tx_hash(payment) is None:
                    continue
                created = _to_utc(payment.created_at)
                if created is not None and created >= cutoff:
                    continue
                out.append((job, payment))
            if len(page) < self.batch_size:
                break
            offset += self.batch_size
        return out

    async def run_once(self) -> dict[str, int]:
        """One sweep. Returns counts for logging and tests."""
        counts = {"candidates": 0, "confirmed": 0, "failed": 0, "skipped": 0, "pending": 0}
        with self._session_factory() as session:
            for job, payment in self._find_candidates(session):
                counts["candidates"] += 1
                counts[await self._reverify(session, job, payment)] += 1
        logger.debug(
            "EVM payment sweep complete: candidates=%s confirmed=%s failed=%s skipped=%s pending=%s",
            counts["candidates"],
            counts["confirmed"],
            counts["failed"],
            counts["skipped"],
            counts["pending"],
        )
        return counts

    async def _reverify(self, session: Any, job: Job, payment: JobPayment) -> str:
        """Re-run receipt verification for one payment; return the counts key."""
        quote = _rebuild_quote(job)
        payment_data = _rebuild_payment_data(payment, job)
        if quote is None or payment_data is None:
            counts_key = "skipped"
        elif self.dry_run:
            logger.info("[DRY-RUN] Would re-verify EVM payment %s (tx %s)", payment.id, _evm_tx_hash(payment))
            return "pending"
        else:
            try:
                await run_in_threadpool(PaymentService(session)._verify_evm_receipt, payment, payment_data, quote)
            except HTTPException:
                # _fail_evm_payment already set status='failed' before raising.
                pass
            except _OPS_ERRORS as e:
                logger.warning("EVM payment sweep re-verify raised for %s: %s", payment.id, e)
                return "pending"
            counts_key = (
                "confirmed" if payment.status == "confirmed" else "failed" if payment.status == "failed" else "pending"
            )
        self._sync_job(session, job, payment)
        return counts_key

    def _sync_job(self, session: Any, job: Job, payment: JobPayment) -> None:
        """Persist the payment outcome and keep job.payment_status in step."""
        now = datetime.now(UTC)
        payment.updated_at = now
        session.add(payment)
        if job.payment_status != payment.status:
            job.payment_status = payment.status
            session.add(job)
        session.commit()

    async def run_forever(self) -> None:
        logger.info(
            "EVM payment sweeper started: interval=%ss min_age=%ss batch=%s dry_run=%s",
            self.interval_seconds,
            self.min_age_seconds,
            self.batch_size,
            self.dry_run,
        )
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                counts = await self.run_once()
            except asyncio.CancelledError:
                raise
            except _OPS_ERRORS as e:
                logger.error("EVM payment sweep failed: %s", e)
                continue
            if counts["candidates"]:
                logger.info(
                    "EVM payment sweep: candidates=%s confirmed=%s failed=%s skipped=%s pending=%s",
                    counts["candidates"],
                    counts["confirmed"],
                    counts["failed"],
                    counts["skipped"],
                    counts["pending"],
                )
