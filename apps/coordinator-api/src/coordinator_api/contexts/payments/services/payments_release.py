"""Escrow release: acceptance window, disputes, release attempts, settlement"""

from __future__ import annotations


from aitbc_shared import JobPayment, PaymentEscrow
from datetime import UTC, datetime
from typing import Any

from starlette.concurrency import run_in_threadpool
from sqlmodel import col, select, update


from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient

from ....custom_types import JobState
from ...infrastructure.domain.job import Job
from ...market.domain.gpu_market import GPURegistry, GPUBooking
from ..acceptance import (
    DISPUTED,
    HELD_STATES,
    META_DISPUTE_REASON,
    META_DISPUTED_AT,
    META_RELEASE_425_FIRST_AT,
    META_RELEASE_ATTEMPTS,
    META_RELEASE_BLOCKED_AT,
    PENDING_ACCEPTANCE,
    SETTLEMENT_FAILED,
    deadline_from,
    max_release_425_seconds,
    max_release_attempts,
    opened_window,
)

from .payments_helpers import (
    _OPS_ERRORS,
    _computation_is_correct,
    _find_http_status_error,
    _parse_settled_at,
    get_receipt_of_record,
)

from .payments_core import PaymentCoreMixin

logger = get_logger(__name__)


class PaymentReleaseMixin(PaymentCoreMixin):
    """Mixin: payment service methods (split from payments.py; pure code motion)."""

    def open_acceptance_window(self, job_id: str, payment_id: str, window_seconds: int) -> datetime | None:
        """Hold a completed job's escrow for the customer to review it (G3).

        Returns the deadline the hold expires at, or None when there is nothing to
        hold -- no such payment, or one that is not escrowed -- so the caller can
        report a settlement failure rather than assume the money is waiting.

        The escrow itself is untouched: the funds stay locked on-chain exactly as
        they were, and only the coordinator's view of what happens next changes.
        """
        payment = self.session.get(JobPayment, payment_id)
        if payment is None or payment.job_id != job_id or payment.status != "escrowed":
            return None
        now = datetime.now(UTC)
        new_meta = opened_window(payment.meta_data, window_seconds, now=now)
        # #1797: CAS the hold — two concurrent opens both read "escrowed";
        # only the writer whose UPDATE lands gets the window.
        won = self._cas_payment_transition(
            payment_id,
            {"escrowed"},
            {"status": PENDING_ACCEPTANCE, "meta_data": new_meta, "updated_at": now},
        )
        if not won:
            self.session.rollback()
            return None
        job = self.session.get(Job, job_id)
        if job is not None:
            job.payment_status = PENDING_ACCEPTANCE
            self.session.add(job)
        self.session.commit()
        self.session.refresh(payment)
        deadline = deadline_from(new_meta)
        logger.info("Payment %s held for acceptance on job %s until %s", payment_id, job_id, deadline)
        return deadline

    def dispute_payment(self, client_id: str, job_id: str, payment_id: str, reason: str) -> bool:
        """Record a customer's rejection of the result (G3).

        The escrow deliberately stays locked. Refunding on the customer's word alone
        would be the mirror image of the problem an acceptance window exists to fix --
        one party settling in its own favour -- so an operator or arbiter rules on it.

        A-1 (Option B): when a dispute is filed, automatically schedule a spot-check
        re-execution so the dispute resolver has evidence rather than only the
        customer's word. The spot-check is best-effort — if the job is not
        deterministic or no eligible miner exists, the dispute still proceeds
        without it and the operator rules manually as before.
        """
        payment = self.session.get(JobPayment, payment_id)
        if payment is None or payment.job_id != job_id:
            return False
        self._require_owned_job(payment.job_id, client_id)
        if payment.status != PENDING_ACCEPTANCE:
            return False
        now = datetime.now(UTC)
        meta = dict(payment.meta_data or {})
        meta[META_DISPUTE_REASON] = reason
        meta[META_DISPUTED_AT] = now.isoformat()
        # #1797: CAS the dispute — a second concurrent dispute (or a release
        # that already moved the row) makes rowcount 0 and loses.
        won = self._cas_payment_transition(
            payment_id,
            {PENDING_ACCEPTANCE},
            {"status": DISPUTED, "meta_data": meta, "updated_at": now},
        )
        if not won:
            self.session.rollback()
            return False
        job = self._require_owned_job(payment.job_id, client_id)
        job.payment_status = DISPUTED
        self.session.add(job)
        self.session.commit()
        self.session.refresh(payment)
        logger.info("Payment %s disputed on job %s: %s", payment_id, job_id, reason)
        # A-1: best-effort spot-check re-execution for dispute evidence.
        try:
            from ...infrastructure.services.spot_check import SpotCheckService

            spot = SpotCheckService(self.session).schedule_if_eligible(job)
            if spot is not None:
                logger.info("Scheduled spot-check %s for disputed job %s", spot.id, job.id)
        except _OPS_ERRORS as e:
            logger.warning("Spot-check scheduling failed for disputed job %s: %s", job.id, e)
        return True

    def get_dispute_evidence(self, job_id: str) -> dict[str, Any] | None:
        """Return spot-check evidence for a disputed job, if any (A-1 / S-3).

        Called by the dispute resolver to surface automatic re-execution
        results alongside the operator's manual ruling.

        The evidence is read from the completed, server-created shadow job
        (``spot_check_for`` points to the original). Client-supplied values on
        the original job's ``constraints`` are never trusted, so forged
        ``spot_check_result`` records cannot drive refunds or bond slashing.
        """
        job = self.session.get(Job, job_id)
        if job is None:
            return None

        from sqlmodel import select

        # Find the completed shadow re-run created by SpotCheckService.
        shadow = (
            self.session.execute(
                select(Job)
                .where(Job.constraints["spot_check_for"].as_string() == job.id)
                .where(Job.state == "COMPLETED")
                .order_by(Job.requested_at.desc())  # type: ignore[attr-defined]
            )
            .scalars()
            .first()
        )
        if not shadow:
            return None
        shadow_constraints = shadow.constraints or {}
        if not shadow_constraints.get("shadow_mode"):
            return None

        result = shadow_constraints.get("spot_check_result")
        if not result or not isinstance(result, dict):
            return None

        # Verify the record is actually for this shadow job and the original.
        if result.get("spot_check_job_id") != shadow.id:
            return None
        if result.get("original_job_id") != job.id:
            return None

        return {
            "match": result.get("match"),
            "original_output_hash": result.get("original_output_hash"),
            "spot_output_hash": result.get("spot_output_hash"),
            "spot_check_job_id": result.get("spot_check_job_id"),
            "completed_at": result.get("completed_at"),
        }

    def _get_receipt_of_record(self, job: Job | None) -> dict[str, Any] | None:
        """Return the canonical receipt for a job.

        The ``Job`` row's ``receipt`` JSON may lag the ``jobreceipt`` table (JSON
        ``MutableDict`` does not always track in-place updates, and the row may be
        written before ZK fields are added). Prefer ``JobReceipt.payload`` when a
        ``receipt_id`` is present; fall back to the denormalised ``Job.receipt``.
        """
        return get_receipt_of_record(self.session, job)

    def _release_attempts_exhausted(
        self,
        payment: JobPayment,
        job_id: str,
        payment_id: str,
        meta: dict[str, Any],
        attempts: int,
    ) -> bool:
        """Move the payment to settlement_failed once release retries hit the bound."""
        if attempts < max_release_attempts():
            return False
        now = datetime.now(UTC)
        meta[META_RELEASE_BLOCKED_AT] = now.isoformat()
        # #1797: CAS — the terminal write must not clobber a row a concurrent
        # op already settled. Losing means the release stops either way.
        won = self._cas_payment_transition(
            payment_id,
            HELD_STATES,
            {"status": SETTLEMENT_FAILED, "meta_data": meta, "updated_at": now},
        )
        if not won:
            self.session.rollback()
            return True
        stuck_job = self.session.get(Job, job_id)
        if stuck_job is not None:
            stuck_job.payment_status = SETTLEMENT_FAILED
            self.session.add(stuck_job)
        self.session.commit()
        logger.critical(
            "Escrow release for job %s payment %s failed %s times; marking settlement_failed "
            "and stopping automatic retries (refund and the admin retry route still work)",
            job_id,
            payment_id,
            attempts,
        )
        return True

    def _release_425_within_bound(
        self,
        meta: dict[str, Any],
        job_id: str,
        payment_id: str,
        now: datetime | None = None,
    ) -> bool:
        """Whether a 425 'not yet' may still restore the release-attempt budget.

        Stamps the first 425 into meta on first sight so a lock that never
        seals cannot suspend the attempt cap forever: inside the bound this
        returns True and the caller restores the spent attempt; past it this
        logs an error naming the job and payment and returns False so the
        normal attempt cap applies and the payment can still go terminal.
        """
        now = now or datetime.now(UTC)
        first_at: datetime | None = None
        raw = meta.get(META_RELEASE_425_FIRST_AT)
        if raw is not None:
            try:
                first_at = datetime.fromisoformat(str(raw))
                if first_at.tzinfo is None:
                    first_at = first_at.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                # A marker that can no longer be parsed cannot be trusted to
                # time the streak either. Restamping `now` here would turn a
                # corrupted clock into a fresh bound (fail-open); the attempt
                # stays spent instead and the corrupt value is kept in meta
                # as evidence rather than silently rewritten.
                logger.error(
                    "Escrow release for job %s payment %s carries an unparseable "
                    "425 deferral marker %r; the streak cannot be timed, so the "
                    "release attempt stays spent",
                    job_id,
                    payment_id,
                    raw,
                )
                return False
        if first_at is None:
            first_at = now
            meta[META_RELEASE_425_FIRST_AT] = now.isoformat()
        elapsed = (now - first_at).total_seconds()
        limit = max_release_425_seconds()
        if elapsed <= limit:
            return True
        logger.error(
            "Escrow release for job %s payment %s deferred by 425 'lock not sealed' "
            "for %.0fs -- past the %ss bound; the release attempt stays spent "
            "and the normal attempt cap now applies",
            job_id,
            payment_id,
            elapsed,
            limit,
        )
        return False

    def _build_release_body(self, reason: str | None, payment: JobPayment, job: Job | None) -> dict[str, Any]:
        release_body: dict[str, Any] = {"reason": reason or "Job completed successfully"}
        meta = payment.meta_data or {}
        if meta.get("energy_is_protected"):
            release_body["energy_is_protected"] = True
            release_body["energy_quote"] = meta.get("energy_quote")
            release_body["energy_quote_digest"] = meta.get("energy_quote_digest")
        provider_address = meta.get("provider_address")
        auto_reinvest_pct = meta.get("auto_reinvest_pct")
        # P2.4: if the payment was created before constraints stored reinvest, fall
        # back to the job's constraints.
        if auto_reinvest_pct is None and job and job.constraints:
            auto_reinvest_pct = job.constraints.get("auto_reinvest_pct")
        if provider_address and auto_reinvest_pct:
            release_body["provider_address"] = provider_address
            release_body["auto_reinvest_pct"] = str(auto_reinvest_pct)
            release_body["auto_reinvest_address"] = provider_address
        # #687: hand the signed receipt of record to the node so the release can
        # seal its RECEIPT_CLAIM — the claim tx carries the record, so apply
        # materialises the receipt row deterministically on every node.
        if job is not None:
            receipt = self._get_receipt_of_record(job)
            if receipt and receipt.get("receipt_id"):
                release_body["receipt"] = receipt
        return release_body

    def _record_release_outcome(
        self,
        payment: JobPayment,
        job: Job,
        payment_id: str,
        job_id: str,
        release_data: dict[str, Any],
    ) -> bool:
        # S-10: a release answer carrying no settlement hash is a claim without
        # proof -- stamping "released" here is what produced a false-paid row
        # for a job the chain never settled. Mark the payment settlement_failed
        # instead: it leaves every sweeper's held set (no automatic re-release)
        # but stays inside REFUNDABLE_STATES, so the manual refund path and the
        # admin retry-release route still reach it. The attempt was already
        # counted by release_payment -- unlike a 425 deferral, this answer is
        # definitive and is not refunded from the retry budget.
        # #1797: the attempt bump and any 425 marker writes went through bulk
        # UPDATEs (synchronize_session=False), so the ORM object is stale —
        # reload before merging meta or the refresh would drop them.
        self.session.refresh(payment)
        tx_hash = release_data.get("tx_hash") or release_data.get("transaction_hash")
        if not tx_hash:
            meta = dict(payment.meta_data or {})
            meta[META_RELEASE_BLOCKED_AT] = datetime.now(UTC).isoformat()
            now = datetime.now(UTC)
            won = self._cas_payment_transition(
                payment_id,
                HELD_STATES,
                {"status": SETTLEMENT_FAILED, "meta_data": meta, "updated_at": now},
            )
            if not won:
                self.session.rollback()
                return False
            if job is not None:
                job.payment_status = SETTLEMENT_FAILED
                self.session.add(job)
            self.session.commit()
            logger.critical(
                "Escrow release for job %s payment %s returned no settlement hash; "
                "marked settlement_failed -- verify the chain before any manual settle",
                job_id,
                payment_id,
            )
            return False
        # Prefer the settlement time the chain reports. On a reconciliation
        # retry that is the original settlement, not this retry, so the payment
        # keeps the time the provider was actually paid.
        settled_at = _parse_settled_at(release_data.get("released_at")) or datetime.now(UTC)
        now = datetime.now(UTC)
        # #1797: CAS the terminal write — a concurrent refund/dispute that
        # already moved the row makes rowcount 0 and this outcome is dropped.
        won = self._cas_payment_transition(
            payment_id,
            HELD_STATES,
            {
                "status": "released",
                "released_at": settled_at,
                "updated_at": now,
                "transaction_hash": tx_hash,
            },
        )
        if not won:
            self.session.rollback()
            logger.warning(
                "Release outcome for job %s payment %s lost the status CAS; the row already moved -- chain says tx %s",
                job_id,
                payment_id,
                tx_hash,
            )
            return False
        self.session.refresh(payment)
        payment.released_at = settled_at
        payment.updated_at = now
        if job is not None:
            job.payment_status = "released"
            self.session.add(job)
        self._mirror_reinvest_on_receipt(payment, job, release_data)
        escrow = self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
        if escrow:
            escrow.is_released = True
            escrow.released_at = settled_at
        self._release_gpu_if_rental(job)
        self.session.commit()
        logger.info("Released payment %s for job %s", payment_id, job_id)
        return True

    def _mirror_reinvest_on_receipt(
        self,
        payment: JobPayment,
        job: Job,
        release_data: dict[str, Any],
    ) -> None:
        reinvest_stake_id = release_data.get("reinvest_stake_id")
        reinvest_amount = release_data.get("reinvest_amount")
        if not reinvest_stake_id and not reinvest_amount:
            return
        meta = dict(payment.meta_data or {})
        if reinvest_stake_id:
            meta["reinvest_stake_id"] = str(reinvest_stake_id)
        if reinvest_amount:
            meta["reinvest_amount"] = str(reinvest_amount)
        meta["reinvest_status"] = "staked" if reinvest_stake_id else "scheduled"
        payment.meta_data = meta
        # Mirror onto the denormalised job receipt so the JobView and
        # the CLI can show it. The JobReceipt payload is the signed
        # record and is not touched; job.receipt is only a display
        # copy. Doing it here rather than in the miner-result router
        # is what matters: the release may equally come from the
        # acceptance sweeper, the client-accept route, the admin
        # retry, or the reconciler, and none of those ran the router
        # helper (GAP-43).
        if job.receipt:
            receipt_with_reinvest = dict(job.receipt)
            receipt_with_reinvest["reinvest_status"] = meta["reinvest_status"]
            if reinvest_stake_id:
                receipt_with_reinvest["reinvest_stake_id"] = meta["reinvest_stake_id"]
            if reinvest_amount:
                receipt_with_reinvest["reinvest_amount"] = meta["reinvest_amount"]
            job.receipt = receipt_with_reinvest

    async def _submit_release(
        self,
        client: AsyncAITBCHTTPClient,
        payment: JobPayment,
        job: Job,
        payment_id: str,
        job_id: str,
        reason: str | None,
    ) -> bool | None:
        """Submit the on-chain release. Returns True settled, False failed on a
        definitive non-425 answer, None when the node answered 425 'lock not
        sealed yet' -- a 'not yet', not a failure. Transport errors and
        ambiguous post-send failures (no response received) are re-raised so
        the caller can keep the 425-deferral marker: an unreachable node says
        nothing about the lock, so it must not end the deferral streak."""
        try:
            release_body = await run_in_threadpool(self._build_release_body, reason, payment, job)
            release_data = await client.post(
                f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}/release",
                json=release_body,
                headers=self._settlement_headers(),
            )
            # The RPC reports success only once the ESCROW_RELEASE transaction is
            # accepted on-chain. Leave the payment escrowed otherwise, so it can be
            # retried rather than recorded as paid with no settlement behind it.
            if release_data.get("success") is False or release_data.get("settlement_status") == "unsettled":
                logger.error(
                    "Escrow release for job %s was not settled on-chain (%s); payment %s stays escrowed",
                    job_id,
                    release_data.get("message"),
                    payment_id,
                )
                return False
            # A response claiming settlement without a hash is a claim without
            # proof (S-10): _record_release_outcome records it as
            # settlement_failed, never released, and returns False.
            return await run_in_threadpool(self._record_release_outcome, payment, job, payment_id, job_id, release_data)
        except NetworkError as e:
            status_error = _find_http_status_error(e)
            if status_error is not None and status_error.response.status_code == 425:
                logger.info(
                    "Escrow release for job %s refused: lock not yet sealed (HTTP 425); payment %s stays escrowed",
                    job_id,
                    payment_id,
                )
                return None
            if status_error is not None:
                logger.error("Failed to release payment: %s", e)
                return False
            # No response was received -- a transport failure or an ambiguous
            # post-send error. Re-raise: the caller clears the 425-deferral
            # marker only on a definitive answer, and this error is none.
            raise

    def _end_425_streak(self, payment_id: str, meta: dict[str, Any]) -> None:
        """End the 425-deferral streak on a definitive non-425 outcome.

        The marker anchors the bound's clock only while 425s actually keep
        arriving. A guard refusal or a definitive submit answer ends the
        streak locally, so leaving the marker would let stale time poison
        the next streak -- the first 425 after the blocker clears would
        measure elapsed from the old stamp and count as instantly
        past-bound. Transport errors and raised exceptions are *no* answer
        and deliberately do not come through here.
        """
        if meta.pop(META_RELEASE_425_FIRST_AT, None) is not None:
            # #1797: meta-only write by id — deliberately NOT status-gated:
            # this runs after the outcome write, so the row is often already
            # terminal (released/settlement_failed) and the stale deferral
            # marker still has to come off.
            self.session.execute(
                update(JobPayment)
                .where(col(JobPayment.id) == payment_id)
                .values(meta_data=meta, updated_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            self.session.commit()

    async def _claim_release_attempt(
        self,
        payment: JobPayment,
        job_id: str,
        payment_id: str,
    ) -> tuple[dict[str, Any], int] | None:
        """Count one release attempt under the status CAS (#1797).

        Returns ``(meta, attempts)`` when the attempt was claimed, or None
        when the retry bound moved the payment to settlement_failed or a
        concurrent op already took the row out of the held set."""
        meta = dict(payment.meta_data or {})
        attempts = int(meta.get(META_RELEASE_ATTEMPTS) or 0)
        if await run_in_threadpool(self._release_attempts_exhausted, payment, job_id, payment_id, meta, attempts):
            return None
        meta[META_RELEASE_ATTEMPTS] = attempts + 1
        # The bump must not land on a row that already left the held set
        # (released/refunded by a concurrent op).
        won = await run_in_threadpool(
            self._cas_payment_transition,
            payment_id,
            HELD_STATES,
            {"meta_data": meta, "updated_at": datetime.now(UTC)},
        )
        if not won:
            await run_in_threadpool(self.session.rollback)
            return None
        # #1824: the CAS UPDATE is uncommitted work, and every non-settling
        # exit below (guard refusal, 425 deferral, transport error) returns
        # without committing -- without this the attempt bump rolls back with
        # the session and META_RELEASE_ATTEMPTS never persists, leaving the
        # retry bound and the 425 window unreachable. Commit the claim now so
        # the attempt is durable no matter which exit the release takes.
        await run_in_threadpool(self.session.commit)
        # The bulk UPDATE bypassed the ORM — reload so later readers (and the
        # 425-marker bookkeeping) see the attempt count that landed.
        await run_in_threadpool(self.session.refresh, payment)
        return meta, attempts

    async def release_payment(self, client_id: str, job_id: str, payment_id: str, reason: str | None = None) -> bool:
        """Release payment from escrow to miner using the blockchain escrow contract."""
        payment = await run_in_threadpool(self.session.get, JobPayment, payment_id)
        if payment is None or payment.job_id != job_id:
            return False
        await run_in_threadpool(self._require_owned_job, payment.job_id, client_id)
        # G3: "pending_acceptance" and "disputed" are escrowed money under another
        # name -- the funds are still locked -- so a release from either is the same
        # on-chain operation. Anything outside HELD_STATES has already settled.
        if payment.status not in HELD_STATES:
            return False
        # A held payment that keeps failing release is retried by every sweeper at
        # every interval forever. Count attempts in meta_data (reassigned, not
        # mutated -- the column is plain JSON) and, past the bound, move the
        # payment to `settlement_failed` so no automatic path picks it up again.
        # The escrow stays funded and refundable; an operator resets the counter
        # through the admin retry-release route once the blocker is fixed.
        claimed = await self._claim_release_attempt(payment, job_id, payment_id)
        if claimed is None:
            return False
        meta, attempts = claimed
        job = await run_in_threadpool(self.session.get, Job, job_id)
        if job is None:
            logger.error("Escrow release blocked for job %s: job not found", job_id)
            await run_in_threadpool(self._end_425_streak, payment_id, meta)
            return False
        if job.state != JobState.completed.value:
            logger.error(
                "Escrow release blocked for job %s payment %s: job state is %s, expected %s",
                job_id,
                payment_id,
                job.state,
                JobState.completed.value,
            )
            await run_in_threadpool(self._end_425_streak, payment_id, meta)
            return False
        receipt = await run_in_threadpool(self._get_receipt_of_record, job)
        if not _computation_is_correct(receipt, job):
            logger.error(
                "Escrow release blocked for job %s payment %s: computation not attested (zk_status=%s, computation_correct=%s)",
                job_id,
                payment_id,
                receipt.get("zk_status") if receipt else None,
                receipt.get("computation_correct") if receipt else None,
            )
            await run_in_threadpool(self._end_425_streak, payment_id, meta)
            return False
        try:
            # Resolve via the facade module: tests patch ``payments.AsyncAITBCHTTPClient``.
            from . import payments as _pm

            client = _pm.AsyncAITBCHTTPClient(timeout=30.0, api_key=self.blockchain_rpc_api_key)
            submitted = await self._submit_release(client, payment, job, payment_id, job_id, reason)
            if submitted is None:
                # 425 'lock not yet sealed' is a 'not yet', not a failure:
                # restore the attempt budget so a long seal delay cannot burn
                # the bound and land the payment in settlement_failed while the
                # escrow is still safely funded. The restoration is itself
                # time-bounded -- a lock that never seals (e.g. the lock tx
                # was dropped) cannot keep the budget suspended forever.
                if self._release_425_within_bound(meta, job_id, payment_id):
                    meta[META_RELEASE_ATTEMPTS] = attempts
                # #1797: same CAS arbiter — only write the meta while the row
                # is still held; a settled row keeps its own meta.
                await run_in_threadpool(
                    self._cas_payment_transition,
                    payment_id,
                    HELD_STATES,
                    {"meta_data": meta, "updated_at": datetime.now(UTC)},
                )
                # #1824: persist the restored attempt count and the 425
                # deferral marker -- this exit returns False without any
                # other commit, so an uncommitted write here silently drops
                # both and the bound's clock never starts.
                await run_in_threadpool(self.session.commit)
                await run_in_threadpool(self.session.refresh, payment)
                return False
            # True or False: both are definitive answers (False can only be an
            # HTTP answer that was not 425 -- transport errors re-raise below),
            # so the deferral streak is over and the marker is cleared. Read
            # the ORM copy: _record_release_outcome may have just merged
            # reinvest keys into it that the local `meta` does not have.
            await run_in_threadpool(self._end_425_streak, payment_id, dict(payment.meta_data or {}))
            return submitted
        except _OPS_ERRORS as e:
            # No definitive outcome (transport failure, ambiguous post-send
            # error): the attempt already counted, but the 425-deferral marker
            # must survive -- an unreachable node is not proof the streak
            # ended, and clearing the marker would restart the bound's clock.
            logger.error("Error releasing payment: %s", e)
            return False

    def _release_gpu_if_rental(self, job: Job) -> None:
        """Mark a rented GPU and its booking as completed/finished when payment is released.

        This is intentionally idempotent: repeated releases only update rows if the
        job is a GPU rental and the booking is still active.
        """
        payload = job.payload or {}
        if payload.get("type") != "gpu_compute":
            return
        gpu_id = payload.get("gpu_id")
        if not gpu_id:
            return
        gpu = self.session.get(GPURegistry, gpu_id)
        if gpu and gpu.status == "booked":
            gpu.status = "available"
            self.session.add(gpu)
        booking = (
            self.session.execute(select(GPUBooking).where(GPUBooking.job_id == job.id, GPUBooking.status == "active").limit(1))
            .scalars()
            .first()
        )
        if booking:
            booking.status = "completed"
            booking.end_time = datetime.now(UTC)
            self.session.add(booking)
