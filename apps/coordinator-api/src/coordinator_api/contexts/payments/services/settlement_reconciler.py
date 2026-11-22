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
from decimal import InvalidOperation

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError

from ....storage.db import get_engine
from ...infrastructure.domain.job import Job
from aitbc_shared import JobPayment

logger = get_logger(__name__)

# Expected failure surface for the settlement reconciler -- it calls
# PaymentService.release_payment, a money path, so the tuple mirrors the
# payment service's own surface: filesystem/JSON, data-shape, runtime,
# SQLAlchemy session errors, lazy imports, httpx transport errors, the
# aitbc error hierarchy, HTTPException (ownership/validation failures the
# service raises), decimal parse failures, timestamp overflows and
# assertion guards. BaseExceptions still propagate
# (asyncio.CancelledError is re-raised explicitly).
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
    httpx.HTTPError,
    InvalidOperation,
    HTTPException,
)


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
        """Completed jobs whose payment is still escrowed past the grace period.

        The gate keys on ``status == 'escrowed'`` alone. It previously also
        required ``escrowed_at IS NOT NULL``, which let an inconsistently
        stamped row (status escrowed, timestamp never written — exactly the
        class that produced the hashless refund rows) escape the sweep forever.
        ``release_payment`` re-verifies on-chain state before doing anything,
        so widening the query is safe; being skipped silently is not.
        """
        # Job.completed_at is a naive-UTC column (SQLModel datetime maps to
        # DateTime without tz); bind a naive cutoff like the reapers do so
        # the comparison does not depend on dialect tz coercion (#1575).
        cutoff = (datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)).replace(tzinfo=None)
        stmt = (
            select(Job)
            .join(JobPayment, Job.payment_id == JobPayment.id)  # type: ignore[arg-type]
            .where(JobPayment.status == "escrowed")
            .where(Job.completed_at.is_not(None))  # type: ignore[union-attr]
            .where(Job.completed_at < cutoff)  # type: ignore[operator]
            .limit(self.batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    def _find_unsealed_release_hashes(self, session: Any) -> list[Any]:
        """Released payments whose recorded tx hash is old enough to have sealed.

        The release endpoint reports the hash of the envelope it *submitted*.
        A pending envelope that later dies (mempool eviction, nonce race) is
        replaced by a resubmission that seals under a different hash, leaving
        ``transaction_hash`` pointing at a transaction that never existed
        on-chain (#2483). This pass audits those rows against the chain.
        """
        newest = datetime.now(UTC) - timedelta(days=30)
        cutoff = (datetime.now(UTC) - timedelta(seconds=self.min_age_seconds)).replace(tzinfo=None)
        stmt = (
            select(JobPayment)
            .where(JobPayment.status == "released")
            .where(JobPayment.transaction_hash.is_not(None))  # type: ignore[union-attr]
            .where(JobPayment.released_at.is_not(None))  # type: ignore[union-attr]
            .where(JobPayment.released_at < cutoff)  # type: ignore[operator]
            .where(JobPayment.released_at > newest.replace(tzinfo=None))  # type: ignore[operator]
            # Newest first: hash_ok rows stay eligible, so without an explicit
            # order the same head of the table would starve the tail (#2483).
            .order_by(JobPayment.released_at.desc())  # type: ignore[union-attr]
            .limit(self.batch_size * 10)
        )
        return list(session.execute(stmt).scalars().all())

    @staticmethod
    async def _recorded_hash_state(client: httpx.AsyncClient, rpc: str, tx_hash: str) -> bool | None:
        """True when the recorded hash resolves to a sealed tx, False on a
        definitive 404, None when the answer is unverifiable."""
        try:
            resp = await client.get(f"{rpc}/rpc/transaction/{tx_hash}")
        except httpx.HTTPError:
            return None
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        return None

    @staticmethod
    async def _sealed_release_hashes(client: httpx.AsyncClient, rpc: str, job_id: str) -> set[str] | None:
        """Confirmed ESCROW_RELEASE hashes for a job; None when unverifiable."""
        try:
            resp = await client.get(
                f"{rpc}/rpc/transactions",
                params={"transaction_type": "ESCROW_RELEASE", "job_id": job_id, "limit": 20},
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            rows = resp.json()
        except ValueError:
            return None
        return {
            str(row.get("transaction_hash") or row.get("tx_hash"))
            for row in rows
            if isinstance(row, dict)
            and row.get("status") == "confirmed"
            and (row.get("transaction_hash") or row.get("tx_hash"))
        }

    @staticmethod
    def _mark_audited(session: Any, payment: Any) -> None:
        """Stamp the audit time so the next pass skips this row for ~20h."""
        meta = dict(payment.meta_data or {})
        meta["release_hash_audit_at"] = datetime.now(UTC).isoformat()
        payment.meta_data = meta
        payment.updated_at = datetime.now(UTC)
        session.add(payment)
        session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)

    @staticmethod
    def _audit_due(payment: Any) -> bool:
        meta = payment.meta_data or {}
        stamped = meta.get("release_hash_audit_at") if isinstance(meta, dict) else None
        if not stamped:
            return True
        try:
            return datetime.now(UTC) - datetime.fromisoformat(str(stamped)) > timedelta(hours=20)
        except ValueError:
            return True

    @staticmethod
    def _readopt_release_hash(session: Any, payment: Any, recorded: str, new_hash: str, counts: dict[str, int]) -> None:
        session.refresh(payment)  # noqa: unawaited-async — sync Session (sqlmodel)
        if payment.status != "released":
            return
        meta = dict(payment.meta_data or {})
        meta["release_tx_hash_corrected"] = {
            "from": recorded,
            "to": new_hash,
            "at": datetime.now(UTC).isoformat(),
        }
        meta["release_hash_audit_at"] = datetime.now(UTC).isoformat()
        payment.transaction_hash = new_hash
        payment.meta_data = meta
        payment.updated_at = datetime.now(UTC)
        session.add(payment)
        session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
        counts["hash_readopted"] += 1
        logger.warning(
            "Payment %s release hash corrected for job %s: %s -> %s (recorded envelope never sealed)",
            payment.id,
            payment.job_id,
            recorded,
            new_hash,
        )

    async def _audit_one_release_hash(
        self,
        client: httpx.AsyncClient,
        rpc: str,
        session: Any,
        payment: Any,
        counts: dict[str, int],
    ) -> None:
        recorded = payment.transaction_hash
        state = await self._recorded_hash_state(client, rpc, recorded)
        if state is None:
            counts["hash_unreachable"] += 1
        elif state:
            counts["hash_ok"] += 1
            self._mark_audited(session, payment)
        else:
            await self._audit_missing_hash(client, rpc, session, payment, recorded, counts)

    async def _audit_missing_hash(
        self,
        client: httpx.AsyncClient,
        rpc: str,
        session: Any,
        payment: Any,
        recorded: str,
        counts: dict[str, int],
    ) -> None:
        sealed = await self._sealed_release_hashes(client, rpc, payment.job_id)
        if sealed is None:
            counts["hash_unreachable"] += 1
            return
        sealed.discard(recorded)
        if len(sealed) == 1:
            self._readopt_release_hash(session, payment, recorded, sealed.pop(), counts)
        elif not sealed:
            counts["hash_unbacked"] += 1
            self._mark_audited(session, payment)
            logger.critical(
                "Payment %s is released but no sealed ESCROW_RELEASE exists for job %s "
                "(recorded hash %s never sealed) -- manual chain verification required",
                payment.id,
                payment.job_id,
                recorded,
            )
        else:
            counts["hash_ambiguous"] += 1
            self._mark_audited(session, payment)
            logger.error(
                "Payment %s job %s has multiple sealed ESCROW_RELEASE hashes %s -- leaving recorded %s",
                payment.id,
                payment.job_id,
                sorted(sealed),
                recorded,
            )

    async def _audit_release_hashes(self) -> dict[str, int]:
        """Verify each released payment's recorded hash actually sealed.

        When the recorded envelope never sealed but exactly one confirmed
        ESCROW_RELEASE exists for the same job, adopt that hash — the payment
        *was* settled, only the recorded pointer was stale. A released payment
        with no sealed release behind it is logged critical: the audit never
        guesses a hash, and an unreachable chain leaves the row untouched.
        """
        counts = {"hash_ok": 0, "hash_readopted": 0, "hash_unbacked": 0, "hash_ambiguous": 0, "hash_unreachable": 0}
        with self._session_factory() as session:
            candidates = [p for p in self._find_unsealed_release_hashes(session) if getattr(p, "transaction_hash", None)]
            if not candidates:
                return counts
            from . import payments as _pm

            rpc = _pm.settings.blockchain_rpc_url.rstrip("/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                for payment in candidates:
                    if not self._audit_due(payment):
                        continue
                    await self._audit_one_release_hash(client, rpc, session, payment, counts)
        return counts

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
                except _OPS_ERRORS as e:
                    counts["failed"] += 1
                    logger.error("Reconciliation raised for job %s: %s", job.id, e)
                    continue
                if settled:
                    job.payment_status = "released"
                    session.add(job)
                    session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
                    counts["settled"] += 1
                    logger.info("Reconciled escrow settlement for job %s", job.id)
                else:
                    counts["failed"] += 1
                    logger.warning("Job %s still unsettled after retry; leaving it escrowed", job.id)
        counts.update(await self._audit_release_hashes())
        # Heartbeat. A pass with nothing to do logs nothing else, so at info level
        # "ran clean" and "the task died" are indistinguishable. Debug so a normal
        # deployment stays quiet but an operator can prove the loop is alive.
        logger.debug(
            "Settlement reconciliation pass complete: scanned=%s retried=%s settled=%s failed=%s "
            "hash_ok=%s hash_readopted=%s hash_unbacked=%s hash_ambiguous=%s hash_unreachable=%s",
            scanned,
            counts["retried"],
            counts["settled"],
            counts["failed"],
            counts["hash_ok"],
            counts["hash_readopted"],
            counts["hash_unbacked"],
            counts["hash_ambiguous"],
            counts["hash_unreachable"],
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
            except _OPS_ERRORS as e:
                logger.error("Settlement reconciliation pass failed: %s", e)
                continue
            if counts["retried"]:
                logger.info(
                    "Settlement reconciliation: retried=%s settled=%s failed=%s",
                    counts["retried"],
                    counts["settled"],
                    counts["failed"],
                )
