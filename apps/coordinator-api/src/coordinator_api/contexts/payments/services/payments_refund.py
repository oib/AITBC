"""Escrow refund: on-chain refund submission and state reconciliation"""

from __future__ import annotations

import httpx

from aitbc_shared import JobPayment, PaymentEscrow
from datetime import UTC, datetime

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool
from sqlmodel import select


from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient

from ....custom_types import JobState
from ...infrastructure.domain.job import Job
from ..acceptance import (
    HELD_STATES,
    REFUNDABLE_STATES,
)

from .payments_helpers import (
    _OPS_ERRORS,
    _find_http_status_error,
    _lookup_chain_lock,
    _lookup_chain_refund,
)

from .payments_core import PaymentCoreMixin

logger = get_logger(__name__)

# Result payload ``status`` values that report the job produced no usable
# output. The miner posts ``{"status": "failed", "error": ...}`` through the
# /result endpoint; storing that payload must not count as delivery for the
# refund gate (#2244).
_FAILED_RESULT_STATUSES = frozenset({"failed", "failure", "error"})

# Keys of the miner result body (``JobSubmitResultBody``) that carry usable
# client output. A failure marker alongside one of these is a partial result
# and still counts as delivered.
_RESULT_OUTPUT_KEYS = ("output", "result", "response", "text", "transcription", "stdout")


def _is_failure_result(result: dict) -> bool:
    """True when a stored result payload reports failure with no usable output."""
    has_output = any(result.get(key) for key in _RESULT_OUTPUT_KEYS)
    if has_output:
        return False
    status_value = result.get("status")
    if isinstance(status_value, str) and status_value.strip().lower() in _FAILED_RESULT_STATUSES:
        return True
    # An error-only report (``{"error": ...}`` with no status field) carries no
    # output the client can use either.
    return bool(result.get("error"))


def _result_is_delivered(job: Job) -> bool:
    """Whether the job's stored result counts as delivered output.

    A miner-reported failure is stored as ``{"status": "failed", "error": ...}``
    and delivers nothing the client can use; treating any truthy
    ``job.result`` as delivery blocked the customer's own refund on exactly
    those jobs (#2244). A failure marker that rode along with real output
    (partial result) still counts as delivered — the anti-double-spend gate
    errs toward blocking.
    """
    result = job.result
    if isinstance(result, dict) and _is_failure_result(result):
        return False
    if result:
        return True
    return job.state == JobState.completed


def _upstream_error_detail(status_error: httpx.HTTPStatusError) -> str | None:
    """Best-effort extraction of the node's ``detail`` message."""
    try:
        body = status_error.response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str) and detail:
            return detail[:300]
    return None


class PaymentRefundMixin(PaymentCoreMixin):
    """Mixin: payment service methods (split from payments.py; pure code motion)."""

    def _mark_refunded(
        self,
        payment: JobPayment,
        job: Job,
        payment_id: str,
        refund_tx_hash: str | None,
    ) -> bool:
        # #1797: CAS the refund mark — a concurrent release that already
        # settled the row must not be overwritten by a stale refund write.
        # "refunded" is allowed through: the reconcile path re-marks an
        # already-refunded row to repair its hash cache, and the write is
        # idempotent there.
        now = datetime.now(UTC)
        won = self._cas_payment_transition(
            payment_id,
            REFUNDABLE_STATES | {"refunded"},
            {
                "status": "refunded",
                "refunded_at": now,
                "updated_at": now,
                "refund_transaction_hash": refund_tx_hash,
            },
        )
        if not won:
            self.session.rollback()
            logger.warning("Refund mark for payment %s lost the status CAS; row already moved", payment_id)
            return False
        self.session.refresh(payment)
        job.payment_status = payment.status
        # A refunded escrow will never pay out, so a job that is still live
        # must die with it — otherwise the assigned miner's later submission
        # passes the assignment/running checks, stores a result nobody paid
        # for, and the client keeps the output for free.
        if job.state in {JobState.queued, JobState.running}:
            job.state = JobState.canceled
            job.error = job.error or "job canceled: escrow refunded"
        self.session.add(job)
        escrow = self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
        if escrow:
            escrow.is_refunded = True
            escrow.is_active = False
            escrow.refunded_at = datetime.now(UTC)
        self.session.commit()
        return True

    async def _fetch_escrow_state(self, client: AsyncAITBCHTTPClient, job_id: str) -> tuple[str | None, bool]:
        """Return (on-chain escrow state, escrow-missing) for the job."""
        try:
            escrow_info = await client.get(f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}")
            return (escrow_info.get("state") if isinstance(escrow_info, dict) else None), False
        except NetworkError as e:
            cause = e.__cause__
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404:
                return None, True
            logger.error("Could not fetch escrow state for %s: %s", job_id, e)
            raise

    async def _reconcile_refund_state(
        self,
        client: AsyncAITBCHTTPClient,
        payment: JobPayment,
        job: Job,
        payment_id: str,
        job_id: str,
    ) -> bool | None:
        """Resolve a refund against the on-chain escrow state.

        Returns True when the refund was recorded locally (unbacked or already
        refunded on-chain), False when the escrow settled and cannot refund, and
        None when a real refund transaction still has to be submitted.
        """
        # Check whether the on-chain escrow is already in a final state.
        escrow_state, escrow_not_found = await self._fetch_escrow_state(client, job_id)

        # H1: unbacked escrow guard. A payment row may be 'escrowed' but the
        # ESCROW_LOCK transaction was never persisted on-chain. No funds moved,
        # so the safe recovery is to mark it refunded and stop retrying.
        # The correct check is whether an ESCROW_LOCK tx exists on-chain, not
        # whether the payment has been released (transaction_hash is a release hash).
        # Only run this for held states; a 'pending' payment has no lock by construction.
        if (
            payment.status in HELD_STATES
            and escrow_not_found
            and not await _lookup_chain_lock(self.blockchain_rpc_url, client, job_id)
        ):
            logger.warning(
                "Escrow for job %s not found on-chain and payment %s has no lock tx; "
                "treating as unbacked escrow and marking refunded",
                job_id,
                payment_id,
            )
            marked = await run_in_threadpool(self._mark_refunded, payment, job, payment_id, None)
            if marked:
                logger.info("Marked unbacked payment %s as refunded for job %s", payment_id, job_id)
            return marked

        if escrow_state == "refunded":
            # B-residue: do not trust a pre-5b0455921 local SHA-256 string.
            # Only accept the DB marker when the same hash is visible on-chain.
            chain_refund_hash = await _lookup_chain_refund(self.blockchain_rpc_url, client, job_id)
            if chain_refund_hash:
                marked = await run_in_threadpool(self._mark_refunded, payment, job, payment_id, chain_refund_hash)
                if marked:
                    logger.info("Marked payment %s as refunded (escrow already refunded) for job %s", payment_id, job_id)
                return marked
            # No on-chain refund exists yet; fall through to submit a real one.

        if escrow_state in {"released", "expired"}:
            logger.error("Escrow for job %s is in %s state, cannot refund", job_id, escrow_state)
            return False
        return None

    async def _submit_refund(
        self,
        client: AsyncAITBCHTTPClient,
        payment: JobPayment,
        job: Job,
        payment_id: str,
        job_id: str,
        reason: str,
    ) -> bool:
        # V23-47: refund is an escrow contract operation, not a wallet endpoint.
        try:
            refund_data = await client.post(
                f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}/refund",
                json={"reason": reason},
                headers=self._settlement_headers(),
            )
            if not refund_data or not refund_data.get("success"):
                logger.error("Blockchain escrow refund failed for %s: %s", job_id, refund_data)
                return False
            marked = await run_in_threadpool(
                self._mark_refunded,
                payment,
                job,
                payment_id,
                refund_data.get("refund_tx_hash") or refund_data.get("transaction_hash"),
            )
            if marked:
                logger.info("Refunded payment %s for job %s", payment_id, job_id)
            return marked
        except NetworkError as e:
            # #2198: an upstream refusal must reach the client as a refusal,
            # not an unhandled 500. 425 = the escrow lock is not sealed yet —
            # retryable, so propagate the status and the node's detail.
            status_error = _find_http_status_error(e)
            if status_error is not None:
                code = status_error.response.status_code
                detail = _upstream_error_detail(status_error) or "escrow settlement refused the refund"
                if code == 425:
                    logger.info("Escrow refund for job %s refused: lock not yet sealed (HTTP 425)", job_id)
                    raise HTTPException(status_code=425, detail=detail) from e
                if 400 <= code < 500:
                    raise HTTPException(status_code=code, detail=detail) from e
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="escrow settlement upstream error; the refund can be retried",
                ) from e
            logger.error("Failed to submit refund transaction: %s", e)
            raise

    async def refund_payment(
        self, client_id: str, job_id: str, payment_id: str, reason: str, *, is_admin: bool = False
    ) -> bool:
        """Refund payment to client"""
        payment = await run_in_threadpool(self.session.get, JobPayment, payment_id)
        if payment is None or payment.job_id != job_id:
            return False
        if is_admin:
            job = await run_in_threadpool(self.session.get, Job, payment.job_id)
            if job is None:
                return False
        else:
            job = await run_in_threadpool(self._require_owned_job, payment.job_id, client_id)
        # B-residue: already-refunded rows may carry a pre-5b0455921 local hash.
        # Fix the denormalised cache, but continue so the chain can return the
        # authoritative on-chain hash.
        if payment.status == "refunded":
            if job.payment_status != "refunded":
                job.payment_status = "refunded"
                self.session.add(job)
                await run_in_threadpool(self.session.commit)
        # G3: a held or disputed payment is still refundable; the escrow never moved.
        # B-residue: already-refunded rows are allowed through so stale hashes can
        # be reconciled against the real on-chain transaction.
        # A payment that was never escrowed cannot be refunded; gating on escrowed_at
        # rather than status prevents the audit invariant from being broken by pending
        # or otherwise non-escrowed rows.
        elif payment.escrowed_at is None or payment.status not in REFUNDABLE_STATES:
            return False
        # A client's refund window ends at delivery: while the payment is held
        # and no usable result exists the client may still pull out, but once
        # output is delivered (pending_acceptance), contested (disputed) or a
        # release has been attempted (settlement_failed), refunding is an
        # arbiter call. A stored failure payload (``{"status": "failed",
        # "error": ...}``) is not delivery — the client received nothing of
        # value and keeps the self-serve refund (#2244).
        # Without this gate a client could collect the result and refund the
        # escrow afterwards — keeping the work and the money.
        delivered = _result_is_delivered(job)
        if not is_admin and payment.status != "refunded" and (payment.status != "escrowed" or delivered):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="the result has been delivered or is under dispute; refunds at this stage need an operator",
            )
        try:
            # Resolve via the facade module: tests patch ``payments.AsyncAITBCHTTPClient``.
            from . import payments as _pm

            client = _pm.AsyncAITBCHTTPClient(timeout=30.0, api_key=self.blockchain_rpc_api_key)
            reconciled = await self._reconcile_refund_state(client, payment, job, payment_id, job_id)
            if reconciled is not None:
                return reconciled
            return await self._submit_refund(client, payment, job, payment_id, job_id, reason)
        except _OPS_ERRORS as e:
            logger.error("Error refunding payment: %s", e)
            raise
