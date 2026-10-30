"""Escrow refund relay service (ESCROW-REFUND-1).

Relays an escrow refund trigger to the settlement-capable chain RPC from
inside the coordinator's network position, mirroring
:mod:`escrow_release_relay`. The chain route
``POST /rpc/escrow/{job_id}/refund`` carries no caller signature — the
node signs the refund with its own settlement key and pays only the
escrow's recorded buyer — so the JWT boundary here is what keeps refund
authority scoped: the escrow's on-chain ``buyer`` must equal the wallet
bound to the JWT subject (admin exempt).

Phase-1 scope (director ruling on #471): **coordinator-minted job_ids
only**. The ``job`` row must exist and be terminal-unpaid
(FAILED/CANCELED/EXPIRED, or past ``expires_at`` for a still-open
QUEUED/RUNNING job); a missing row means a market-minted escrow, which
stays a settlement-node refund. COMPLETED is never refundable through
the relay. A sealed on-chain ``software_job``/``completed`` record that
contradicts the coordinator row fails closed, as does a failed lookup.

The relay sends no ``amount``: the chain refunds locked minus
already-released legs, clamped to the sealed lock.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, select

from aitbc.network import AsyncAITBCHTTPClient
from aitbc_shared import JobPayment

from ....storage import get_session
from ...infrastructure.domain.job import Job
from ..domain.escrow_refund_relay import EscrowRefundRelay
from .escrow_relay import EscrowRelayService
from .payments import _find_http_status_error

logger = logging.getLogger(__name__)

# Refund reasons the relay forwards verbatim to the chain.
REFUND_REASONS = frozenset({"buyer_requested", "job_failed", "timeout", "expired"})

# Coordinator job states in which the lock may be refunded at once. COMPLETED
# is deliberately absent: a finished job's escrow is released, never refunded.
_TERMINAL_UNPAID_STATES = frozenset({"FAILED", "CANCELED", "EXPIRED"})


def _chain_detail(exc: BaseException, fallback: str) -> tuple[int | None, Any]:
    """Extract (status_code, detail) from a wrapped chain HTTP error."""
    status_error = _find_http_status_error(exc)
    if status_error is None:
        return None, fallback
    detail: Any = fallback
    try:
        resp_body = status_error.response.json()
        if isinstance(resp_body, dict) and isinstance(resp_body.get("detail"), str):
            detail = resp_body["detail"]
    except ValueError:
        pass
    return status_error.response.status_code, detail


def _to_utc(dt: datetime | None) -> datetime | None:
    """Normalize a possibly-naive stored datetime to UTC for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class EscrowRefundRelayService(EscrowRelayService):
    """Relay escrow refund triggers to the chain RPC.

    Inherits the wallet-binding and buyer-binding checks from
    :class:`EscrowRelayService`; the dedup shape (job_id, no signed
    payload) matches the release relay.
    """

    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        super().__init__(session)

    async def _fetch_escrow(self, client: AsyncAITBCHTTPClient, job_id: str) -> dict[str, Any]:
        """Read the escrow row from the chain; 404s pass through."""
        try:
            escrow = await client.get(f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}")
        except Exception as exc:
            code, detail = _chain_detail(exc, "the escrow lookup failed on the settlement node")
            if code is not None and 400 <= code < 500:
                raise HTTPException(status_code=code, detail=detail) from exc
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the escrow refund relay could not reach the settlement node; the request can be retried",
            ) from exc
        if not isinstance(escrow, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the settlement node returned an unexpected escrow payload",
            )
        return escrow

    async def _post_refund(self, client: AsyncAITBCHTTPClient, job_id: str, forward: dict[str, Any]) -> dict[str, Any]:
        """POST the refund to the settlement node; 4xx pass through, else 502."""
        try:
            return await client.post(
                f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}/refund",
                json=forward,
            )
        except Exception as exc:
            code, detail = _chain_detail(exc, "the node refused the escrow refund")
            if code is not None and 400 <= code < 500:
                # Chain 4xx (including the 425 "lock not yet sealed" retryable
                # refusal): the node's message is a domain message safe to
                # pass through at the same status code.
                raise HTTPException(status_code=code, detail=detail) from exc
            # Timeout / 5xx / ambiguous post-send failure: the refund may
            # still have landed — the replay dedup makes a retry safe.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the escrow refund relay could not reach the settlement node; the request can be retried",
            ) from exc

    async def _check_no_completed_job_record(self, client: AsyncAITBCHTTPClient, job_id: str) -> None:
        """Fail closed if the chain shows a sealed software_job=completed record.

        The coordinator ``job`` row is authoritative for terminal-unpaid
        state, but a buyer-signed on-chain completion record that
        contradicts it means the two evidences disagree — refuse rather
        than refund money the provider may have earned. A lookup failure
        is a refusal too: the check cannot be skipped by knocking out the
        query.
        """
        try:
            # ``/rpc/transactions`` answers a bare list — ``get_json``, not
            # ``get`` (which refuses non-object bodies).
            txs = await client.get_json(
                f"{self.blockchain_rpc_url}/rpc/transactions",
                params={"transaction_type": "GPU_MARKET", "job_id": job_id, "limit": 100},
            )
        except HTTPException:
            raise
        except Exception as exc:
            code, detail = _chain_detail(exc, "the on-chain job-record lookup failed")
            logger.warning(
                "Escrow refund refused: job-record lookup failed for job_id=%s (chain status=%s)",
                job_id,
                code,
            )
            if code is not None and 400 <= code < 500:
                raise HTTPException(status_code=code, detail=detail) from exc
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the escrow refund relay could not verify the on-chain job record; the request can be retried",
            ) from exc
        if not isinstance(txs, list):
            logger.warning("Escrow refund refused: unexpected transactions payload for job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="the settlement node returned an unexpected transactions payload",
            )
        for tx in txs:
            if not isinstance(tx, dict):
                continue
            payload = tx.get("payload") or {}
            if (
                tx.get("block_height") is not None
                and payload.get("action") == "software_job"
                and payload.get("status") == "completed"
            ):
                logger.warning(
                    "Escrow refund refused: sealed software_job=completed record contradicts the job row "
                    "for job_id=%s (tx_hash=%s)",
                    job_id,
                    tx.get("tx_hash"),
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"on-chain record shows job_id={job_id} completed; a completed job is not refundable",
                )

    def _check_job_refundable(self, client_id: str, is_admin: bool, job_id: str) -> None:
        """The coordinator job-state gate — phase-1 scope enforcement.

        A missing ``job`` row means the escrow was minted market-side; the
        relay structurally refuses those (they stay settlement-node
        refunds). COMPLETED is never refundable, whatever the clock says.
        A held ``job_payments`` row in released/refunded state is secondary
        evidence and short-circuits before the chain call.
        """
        job = self.session.get(Job, job_id)
        if job is None:
            logger.warning("Escrow refund refused: no coordinator job row for job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no coordinator job for job_id={job_id}; market-minted escrows are refunded on the settlement node",
            )
        if not is_admin and job.client_id != client_id:
            logger.warning(
                "Escrow refund refused: job_id=%s belongs to a different client (caller=%s)",
                job_id,
                client_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="job does not belong to this credential",
            )

        payment: JobPayment | None = (
            self.session.execute(select(JobPayment).where(JobPayment.job_id == job_id)).scalars().first()
        )
        if payment is not None:
            if payment.status == "released" or payment.released_at is not None:
                logger.warning("Escrow refund refused: job_payments already released for job_id=%s", job_id)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"payment for job_id={job_id} has already been released",
                )
            if payment.status == "refunded" or payment.refunded_at is not None:
                row = EscrowRefundRelay(
                    client_id=client_id,
                    job_id=job_id,
                    tx_hash=payment.refund_transaction_hash,
                    contract_id=None,
                )
                stored = self._insert_or_existing(row)
                raise _AlreadyRefunded(stored if stored is not None else row)

        if job.state == "COMPLETED":
            logger.warning(
                "Escrow refund refused: COMPLETED job_id=%s is never refundable (client_id=%s)",
                job_id,
                client_id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"job_id={job_id} is COMPLETED; a completed job is released, not refunded",
            )
        if job.state not in _TERMINAL_UNPAID_STATES:
            # QUEUED/RUNNING (or an unrecognised state): refundable only once
            # the job's own expiry has passed — the same bound the
            # agent-coordinator sweeper refunds on.
            expires_at = _to_utc(job.expires_at)
            if expires_at is None or expires_at > datetime.now(UTC):
                logger.warning(
                    "Escrow refund refused: job_id=%s is %s and not past expires_at (client_id=%s)",
                    job_id,
                    job.state,
                    client_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"job_id={job_id} is {job.state} and has not expired",
                )

    def _stored_result(self, row: EscrowRefundRelay) -> dict[str, Any]:
        return {
            "success": True,
            "contract_id": row.contract_id,
            "tx_hash": row.tx_hash,
            "refund_tx_hash": row.tx_hash,
            "duplicate": True,
        }

    def _insert_or_existing(self, row: EscrowRefundRelay) -> EscrowRefundRelay | None:
        """Insert *row*; on a concurrent duplicate insert return the stored row instead.

        Two simultaneous refunds can both pass the dedup lookup — the loser
        hits the unique job_id index. It must not surface a 500: the stored
        row is the correct replay result.
        """
        self.session.add(row)
        try:
            self.session.commit()
            return None
        except IntegrityError:
            self.session.rollback()
            return (
                self.session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == row.job_id)).scalars().first()
            )

    async def refund(self, client_id: str, is_admin: bool, body: dict[str, Any]) -> dict[str, Any]:
        """Validate, dedup and forward the escrow refund to the chain.

        Returns a dict with ``refund_tx_hash``/``contract_id``/``duplicate``
        (plus any fields the chain reported).
        """
        job_id = body.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="job_id is required",
            )
        reason = body.get("reason") or "buyer_requested"
        if reason not in REFUND_REASONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"reason must be one of {sorted(REFUND_REASONS)}",
            )

        client = AsyncAITBCHTTPClient(timeout=10.0, api_key=self.blockchain_rpc_api_key)

        # Ownership first: the buyer check must run before any dedup or
        # already-refunded return, or a logged-in caller who merely knows a
        # job_id could read that escrow's tx_hash/contract_id.
        escrow = await self._fetch_escrow(client, job_id)
        buyer = escrow.get("buyer")
        if not is_admin:
            if not isinstance(buyer, str) or not buyer:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="the settlement node did not report the escrow buyer",
                )
            await run_in_threadpool(self._check_buyer_binding, client_id, buyer)

        # Dedup: a prior relay row settles the job — return it without a
        # chain call so a replayed request can never double-refund.
        existing: EscrowRefundRelay | None = await run_in_threadpool(
            lambda: self.session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == job_id)).scalars().first()
        )
        if existing is not None:
            return self._stored_result(existing)

        state = escrow.get("state")
        if state == "refunded" or escrow.get("refunded_at"):
            # Already refunded on-chain: record the outcome and return it —
            # a second refund POST is unnecessary and unsafe to repeat.
            row = EscrowRefundRelay(
                client_id=client_id,
                job_id=job_id,
                tx_hash=escrow.get("refund_tx_hash"),
                contract_id=escrow.get("contract_id"),
            )
            stored = await run_in_threadpool(self._insert_or_existing, row)
            return self._stored_result(stored if stored is not None else row)
        if state == "released" or escrow.get("released_at"):
            logger.warning("Escrow refund refused: escrow already released for job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Escrow for job_id={job_id} has already been released",
            )

        # Phase-1 gate: coordinator job must exist and be terminal-unpaid;
        # secondary payment evidence; then the on-chain conflict check.
        try:
            await run_in_threadpool(self._check_job_refundable, client_id, is_admin, job_id)
        except _AlreadyRefunded as prior:
            return self._stored_result(prior.row)
        await self._check_no_completed_job_record(client, job_id)

        chain_response = await self._post_refund(client, job_id, {"reason": reason})

        refund_tx_hash = chain_response.get("refund_tx_hash") if isinstance(chain_response, dict) else None
        contract_id = chain_response.get("contract_id") if isinstance(chain_response, dict) else None
        row = EscrowRefundRelay(client_id=client_id, job_id=job_id, tx_hash=refund_tx_hash, contract_id=contract_id)
        stored = await run_in_threadpool(self._insert_or_existing, row)
        if stored is not None:
            # Concurrent identical refund: the row landed first — the chain
            # call may or may not have sealed; return the stored result.
            return self._stored_result(stored)
        # Audit: one line per relay — client, job, reason and the tx, never payload detail.
        logger.info(
            "Escrow refund relayed: client_id=%s job_id=%s contract_id=%s refund_tx_hash=%s reason=%s",
            client_id,
            job_id,
            contract_id,
            refund_tx_hash,
            reason,
        )
        result: dict[str, Any] = dict(chain_response) if isinstance(chain_response, dict) else {}
        result.setdefault("success", True)
        result["contract_id"] = contract_id
        result["refund_tx_hash"] = refund_tx_hash
        result["duplicate"] = bool(result.get("duplicate", False))
        return result


class _AlreadyRefunded(Exception):
    """Internal short-circuit: job_payments already shows the refund."""

    def __init__(self, row: EscrowRefundRelay) -> None:
        super().__init__()
        self.row = row
