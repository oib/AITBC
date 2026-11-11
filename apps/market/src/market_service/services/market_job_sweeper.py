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

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger
from aitbc.market import BlockchainRPCClient, OfferStatus

from ..config import settings
from ..domain.market import Bid, MarketJob, MarketJobPayment, MarketOffer
from ..domain.offer_status import spellings_of
from ..storage import get_session_context

logger = get_logger(__name__)

# A 'not yet' settlement answer (404, {success:false}, or any raised error)
# defers a job's escrow only this long before one confirming read decides
# its fate. Six hours mirrors the coordinator's 425-deferral bound: far
# above follower lag and any restart window, bounded churn instead of
# either instant-terminal or forever-silent.
DEFAULT_SETTLE_DEFERRAL_MAX_SECONDS = 6 * 3600
META_SETTLE_DEFERRAL_FIRST_AT = "settle_deferral_first_at"


def _settleable_job_clause():
    """#1783: jobs under an open dispute (disputed_at set, dispute_cleared_at
    unset) are invisible to both the release and refund passes."""
    return or_(col(MarketJob.disputed_at).is_(None), col(MarketJob.dispute_cleared_at).is_not(None))


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
        counts = {"released": 0, "refunded": 0, "failed": 0, "offers_expired": 0, "disputed_frozen": 0}

        async with self._session_factory() as session:
            now = datetime.now(UTC)
            now_naive = now.replace(tzinfo=None)

            await self._expire_stale_jobs(session, now_naive)
            await self._expire_stale_reservations(session, now_naive)
            counts["offers_expired"] = await self._expire_stale_offers(session, now_naive)

            # #1783: an open dispute freezes settlement — count them loudly
            # each sweep so a frozen escrow is never silent.
            open_disputes = (
                await session.execute(
                    select(func.count())
                    .select_from(MarketJob)
                    .where(col(MarketJob.disputed_at).is_not(None), col(MarketJob.dispute_cleared_at).is_(None))
                )
            ).scalar() or 0
            if open_disputes:
                logger.warning("MarketJobSweeper: %s job(s) under dispute freeze — settlement skipped", open_disputes)
                counts["disputed_frozen"] = int(open_disputes)

            # 1. Release: jobs that completed and are past the grace period.
            # EXPIRED is deliberately absent: expiry only ever lands on
            # QUEUED/RUNNING (unfinished) jobs, whose escrow belongs to the
            # buyer — the refund pass below handles them. Releasing here
            # would pay the provider for work never done (#v10 item 13).
            # expires_at/updated_at are naive-UTC columns (domain
            # default_factory strips tzinfo); bind naive cutoffs so the
            # comparisons do not depend on dialect-specific tz coercion of
            # an aware datetime (#1575).
            release_cutoff = (now - timedelta(seconds=self.refund_grace_seconds)).replace(tzinfo=None)

            release_stmt = (
                select(MarketJob, MarketJobPayment)
                .join(MarketJobPayment, col(MarketJob.payment_id) == MarketJobPayment.id)
                .where(col(MarketJobPayment.status) == "escrowed")
                .where(col(MarketJobPayment.escrowed_at).is_not(None))
                .where(_settleable_job_clause())
                .where(col(MarketJob.state).in_({"COMPLETED"}))
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
            min_age = (now - timedelta(seconds=self.min_age_seconds)).replace(tzinfo=None)

            refund_stmt = (
                select(MarketJob, MarketJobPayment)
                .join(MarketJobPayment, col(MarketJob.payment_id) == MarketJobPayment.id)
                .where(col(MarketJobPayment.status).in_({"escrowed", "refund_pending"}))
                .where(col(MarketJobPayment.escrowed_at).is_not(None))
                .where(_settleable_job_clause())
                # EXPIRED joins FAILED/CANCELED: an expired job is unfinished
                # by definition, so its escrowed payment refunds the buyer
                # even when the expire path missed the refund_pending flip
                # (e.g. the access-token lazy expiry).
                .where(
                    (col(MarketJob.state).in_({"FAILED", "CANCELED", "EXPIRED"}))
                    | (col(MarketJobPayment.status) == "refund_pending")
                )
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

    async def _expire_stale_jobs(self, session: AsyncSession, now_naive: datetime) -> None:
        """Expire QUEUED/RUNNING jobs past expires_at -> EXPIRED (#1554).

        ttl_seconds was stored but never enforced and only the access-token
        path lazily expired jobs, so an escrowed job could sit forever. An
        escrowed payment flips to refund_pending so the refund pass below
        returns the funds to the buyer — an expired unfinished job must not
        pay the provider.
        """
        expire_stmt = (
            select(MarketJob)
            .where(col(MarketJob.state).in_({"QUEUED", "RUNNING"}))
            .where(col(MarketJob.expires_at).is_not(None))
            .where(col(MarketJob.expires_at) < now_naive)
            .limit(self.batch_size)
        )
        expire_result = await session.execute(expire_stmt)
        for job in expire_result.scalars().all():
            job.state = "EXPIRED"
            job.updated_at = now_naive
            if job.payment_id:
                pay = await session.get(MarketJobPayment, job.payment_id)
                if pay is not None and pay.status == "escrowed":
                    pay.status = "refund_pending"
                    pay.updated_at = now_naive
                    session.add(pay)
                    job.payment_status = "refund_pending"
            session.add(job)
            logger.info("Market job %s expired (expires_at=%s)", job.id, job.expires_at)

    async def _expire_stale_reservations(self, session: AsyncSession, now_naive: datetime) -> None:
        """Expire pending bids and release stale offer reservations (#1554).

        Two holds used to live forever: a ``pending`` Bid awaiting its
        on-chain payment, and a MarketOffer stuck in ``reserved``/``booked``
        after a match or booking whose follow-through never arrived. Bids
        carry ``expires_at``; offers carry ``attributes['_reserved_until']``
        (the shared model has no expires_at column — see book_offer). Offers
        in ``in_use`` run paid work and are never touched; legacy held rows
        without the marker are left alone rather than guessed at.
        """
        bid_stmt = (
            select(Bid)
            .where(col(Bid.status) == "pending")
            .where(col(Bid.expires_at).is_not(None))
            .where(col(Bid.expires_at) < now_naive)
            .limit(self.batch_size)
        )
        for bid in (await session.execute(bid_stmt)).scalars().all():
            bid.status = "expired"
            session.add(bid)
            logger.info("Pending bid %s expired (expires_at=%s)", bid.id, bid.expires_at)

        offer_stmt = select(MarketOffer).where(col(MarketOffer.status).in_({"reserved", "booked"})).limit(self.batch_size * 4)
        for offer in (await session.execute(offer_stmt)).scalars().all():
            attrs = offer.attributes or {}
            raw_until = attrs.get("_reserved_until")
            if not raw_until:
                continue
            try:
                reserved_until = datetime.fromisoformat(str(raw_until))
            except (TypeError, ValueError):
                continue
            if reserved_until.tzinfo is not None:
                reserved_until = reserved_until.replace(tzinfo=None)
            if reserved_until >= now_naive:
                continue
            # RESERVED -> AVAILABLE is a legal FSM transition; "booked" maps
            # to RESERVED so the same edge applies. Clear the marker so a
            # later re-reservation stamps a fresh deadline.
            offer.status = "available"
            new_attrs = dict(attrs)
            new_attrs.pop("_reserved_until", None)
            offer.attributes = new_attrs
            session.add(offer)
            logger.info("Offer %s reservation expired; released to available", offer.id)

    async def _expire_stale_offers(self, session: AsyncSession, now_naive: datetime) -> int:
        """Expire AVAILABLE-state offers past ``expires_at`` (#1554).

        The shared MarketOffer model gained an ``expires_at`` column; NULL
        means the listing never expires (backward compatible). Only the
        available listing lapses — booked/reserved holds keep their own
        ``_reserved_until`` deadline and in_use rows run paid work.
        AVAILABLE -> EXPIRED is a legal FSM edge.
        """
        stmt = (
            select(MarketOffer)
            .where(col(MarketOffer.expires_at).is_not(None))
            .where(col(MarketOffer.expires_at) < now_naive)
            .where(col(MarketOffer.status).in_(spellings_of(OfferStatus.AVAILABLE)))
            .limit(self.batch_size)
        )
        expired = 0
        for offer in (await session.execute(stmt)).scalars().all():
            offer.status = OfferStatus.EXPIRED.value
            session.add(offer)
            expired += 1
            logger.info("Offer %s expired (expires_at=%s)", offer.id, offer.expires_at)
        return expired

    async def _release_payment(
        self,
        session: AsyncSession,
        job: MarketJob,
        payment: MarketJobPayment,
    ) -> bool:
        """Release escrow to the provider. Returns True on success."""
        # The chain escrow is keyed by job_id — the market job id IS the
        # escrow's job_id. escrow_contract_id persists that same job.id at
        # creation (#1634) but is informational only; the RPC path key is
        # always job.id, never the column (#1564).
        escrow_key = job.id
        try:
            result = await self._rpc_client.release_escrow(escrow_key)
        except Exception as e:  # noqa: BLE001 - any raised answer is a not-yet — shares the bounded deferral
            # Any raised answer (425 'lock not sealed', 5xx, transport) is a
            # 'not yet' too -- it shares the bounded deferral instead of
            # retrying forever and silently.
            return await self._settlement_not_yet(session, job, payment, f"{type(e).__name__}: {e}", escrow_key, "released")
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
        return await self._settlement_not_yet(session, job, payment, outcome, escrow_key, "released")

    async def _refund_payment(
        self,
        session: AsyncSession,
        job: MarketJob,
        payment: MarketJobPayment,
    ) -> bool:
        """Refund escrow to the buyer. Returns True on success."""
        # Same canonical binding as release: the escrow path key is the
        # market job id, not escrow_contract_id (#1564).
        escrow_key = job.id
        try:
            result = await self._rpc_client.refund_escrow(escrow_key)
        except Exception as e:  # noqa: BLE001 - any raised answer is a not-yet — shares the bounded deferral
            return await self._settlement_not_yet(session, job, payment, f"{type(e).__name__}: {e}", escrow_key, "refunded")
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
        return await self._settlement_not_yet(session, job, payment, outcome, escrow_key, "refunded")

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
        intended: str,
    ) -> bool:
        """A 'not yet' settlement answer defers, bounded by settle_max_seconds.

        Inside the bound the row stays selectable and the next sweep retries;
        the first deferral stamps ``meta_data['settle_deferral_first_at']``.
        Past the bound one ``GET /escrow/{id}`` read converts the guess into
        evidence: absent -> terminal ``settlement_failed``; a released or
        refunded row with a sealed tx hash -> adopt that verdict (reality
        wins even when the row's kind is not the ``intended`` one -- the row
        is authoritative for where the money went); anything else (still
        locked, hashless or unsealed verdict, or a failed read) -> keep
        deferring with a loud log line.
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
        except Exception as e:  # noqa: BLE001 - read error captured, deferral bookkeeping continues
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
        state = escrow.get("state") if escrow is not None else None
        if read_error is None and escrow is not None and state in {"released", "refunded"}:
            tx_hash = escrow.get("release_tx_hash") if state == "released" else escrow.get("refund_tx_hash")
            if not tx_hash:
                # A verdict row without a landed hash is the S-8 dead-hash
                # shape: never adopt 'settled' from a hash that may never
                # have sealed. Defer and let an operator look.
                logger.error(
                    "Escrow settlement for job %s payment %s deferred %.0fs past bound; "
                    "escrow reports %s but its tx hash is empty -- still deferring",
                    job.id,
                    payment.id,
                    elapsed,
                    state,
                )
                return False
            # Non-empty is not enough: the S-8 dead-hash shape is a hash that
            # is present on the row but never sealed in a block. Adopt only
            # once GET /rpc/transaction/{hash} finds it with a block height.
            tx: dict[str, Any] | None = None
            seal_error: Exception | None = None
            try:
                tx = await self._rpc_client.get_transaction(tx_hash)
            except Exception as e:  # noqa: BLE001 - seal error captured — unsealed reads skip, never raise
                seal_error = e
            if tx is None or tx.get("block_height") is None:
                logger.error(
                    "Escrow settlement for job %s payment %s deferred %.0fs past bound; "
                    "escrow reports %s but tx %s %s -- still deferring",
                    job.id,
                    payment.id,
                    elapsed,
                    state,
                    tx_hash,
                    f"lookup failed ({seal_error})"
                    if seal_error is not None
                    else "is not found on the chain"
                    if tx is None
                    else "is present but not sealed (no block height)",
                )
                return False
            if state != intended:
                # Reality wins: the row is authoritative for where the money
                # went, so a settled escrow is adopted even when it is not the
                # kind this sweep intended -- marking it 'failed' would strand
                # a settled escrow, deferring forever is noise.
                logger.error(
                    "Escrow settlement for job %s payment %s: sweeper intended %s but "
                    "the escrow reports %s -- adopting the row's verdict",
                    job.id,
                    payment.id,
                    intended,
                    state,
                )
            self._adopt_escrow_verdict(session, job, payment, meta, escrow, now)
            logger.info(
                "Escrow settlement for job %s payment %s deferred %.0fs past bound; "
                "escrow read reports %s -- adopting the verdict",
                job.id,
                payment.id,
                elapsed,
                state,
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
