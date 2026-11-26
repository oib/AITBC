"""Escrow refund relay service (ESCROW-REFUND-1).

Relays an escrow refund trigger to the settlement-capable chain RPC from
inside the coordinator's network position, mirroring
:mod:`escrow_release_relay`. The chain route
``POST /rpc/escrow/{job_id}/refund`` carries no caller signature — the
node signs the refund with its own settlement key and pays only the
escrow's recorded buyer — and since #1917 it additionally requires the
settlement credential as ``X-Settlement-Key`` on top of ``X-API-Key``;
this service forwards ``blockchain_rpc_settlement_api_key`` as that
header. The JWT boundary here is what keeps refund
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
from ....utils.client_resolver import resolve_client
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
                headers=self._settlement_headers(),
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
        A held ``job_payments`` row in released state is secondary evidence
        and refuses; a refunded marker is *not* — the node marks
        ``refunded_at`` at submission and this gate only runs after the
        escrow read proved the chain record is NOT refunded, so a local
        refunded marker here is stale evidence (#3032) and the refund
        re-drives instead of answering success.
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
            # #3032: a local refunded marker is deliberately NOT trusted
            # here — this gate only runs after the escrow read proved the
            # chain record is not refunded, so the marker is stale
            # (submission-time write or a dead envelope). It must not answer
            # success; fall through and re-drive the refund.

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

    def _canonical_client_id(self, client_id: str) -> str:
        """Resolve the caller ref to the canonical ``users.id``.

        ``job.client_id`` and ``wallets.user_id`` store canonical ids while
        the JWT ``sub`` may be any client ref (username, wallet address).
        Same normalization ``_require_owned_job`` applies — an unresolvable
        ref falls back to the raw string, which then simply fails the
        ownership compare (#2814).
        """
        try:
            resolved, _ = resolve_client(self.session, client_id, auto_create=False)
            return resolved
        except ValueError:
            return client_id

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
        # job_id could read that escrow's tx_hash/contract_id. Both binding
        # checks compare against canonical users.id — the JWT sub may be a
        # username or wallet ref (#2814).
        escrow = await self._fetch_escrow(client, job_id)
        buyer = escrow.get("buyer")
        canonical_client_id = await run_in_threadpool(self._canonical_client_id, client_id)
        if not is_admin:
            if not isinstance(buyer, str) or not buyer:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="the settlement node did not report the escrow buyer",
                )
            await run_in_threadpool(self._check_buyer_binding, canonical_client_id, buyer)

        state = escrow.get("state")
        escrow_refunded = state == "refunded" or bool(escrow.get("refunded_at"))
        escrow_released = state == "released" or bool(escrow.get("released_at"))

        # Dedup: a prior relay row with a tx_hash settles the job — return
        # it without a chain call so a replayed request can never
        # double-refund. A hashless row is not proof of settlement and
        # falls through to re-drive (#2814). The escrow state fetched above
        # is the arbiter (#3008): the node marks refunded_at at submission
        # and its sweeper demotes the row when the envelope proves
        # unsealed, so "escrow not refunded" means the stored hash is dead —
        # replaying it would tell the buyer they were refunded while the
        # funds stay locked. Pending and confirmed refunds both read as
        # refunded on the node record, so live dedup is preserved.
        existing: EscrowRefundRelay | None = await run_in_threadpool(
            lambda: self.session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == job_id)).scalars().first()
        )
        # #3032: the chain record is authoritative for *which* refund
        # landed — a divergent cached hash is healed, never replayed.
        adopted = await self._adopt_authoritative_hash(job_id, escrow, existing, escrow_refunded=escrow_refunded)
        if adopted is not None:
            return adopted
        replay = self._dedup_replay(existing, escrow_refunded=escrow_refunded)
        if replay is not None:
            return replay
        if existing is not None and existing.tx_hash:
            # Dead stored attempt: clear the hash so the re-drive below
            # records the replacement instead of the _finish_refund
            # concurrent-duplicate branch replaying the dead hash.
            await run_in_threadpool(self._clear_dead_dedup_hash, existing)

        if escrow_refunded:
            # Already refunded on-chain: record (or heal) the outcome and
            # return it — a second refund POST is unnecessary and unsafe.
            return await self._record_settled_refund(client_id, job_id, escrow, existing)
        if escrow_released:
            logger.warning("Escrow refund refused: escrow already released for job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Escrow for job_id={job_id} has already been released",
            )

        # Phase-1 gate: coordinator job must exist and be terminal-unpaid;
        # secondary payment evidence; then the on-chain conflict check.
        await run_in_threadpool(self._check_job_refundable, canonical_client_id, is_admin, job_id)
        await self._check_no_completed_job_record(client, job_id)

        chain_response = await self._post_refund(client, job_id, {"reason": reason})
        return await self._finish_refund(client, client_id, job_id, reason, chain_response, existing)

    async def _adopt_authoritative_hash(
        self,
        job_id: str,
        escrow: dict[str, Any],
        existing: EscrowRefundRelay | None,
        *,
        escrow_refunded: bool,
    ) -> dict[str, Any] | None:
        """#3032: heal a stale cached hash to the chain's authoritative one.

        When the escrow reads refunded and its ``refund_tx_hash`` names a
        different attempt than the dedup row cached, the cache is stale —
        adopt the chain's hash and return the corrected stored result. No
        second submission: the escrow already reads refunded. Returns None
        when there is nothing to adopt (no row, no cached hash, escrow not
        refunded, hashes agree, or the chain names no hash).
        """
        if existing is None or not existing.tx_hash or not escrow_refunded:
            return None
        authoritative = escrow.get("refund_tx_hash")
        if not authoritative or authoritative == existing.tx_hash:
            return None
        stale = existing.tx_hash
        await run_in_threadpool(
            self._fill_dedup_row,
            existing,
            tx_hash=authoritative,
            contract_id=escrow.get("contract_id") or existing.contract_id,
        )
        logger.warning(
            "Escrow refund relay adopted authoritative hash %s for job_id=%s (cached %s was stale)",
            authoritative,
            job_id,
            stale,
        )
        return self._stored_result(existing)

    @staticmethod
    def _chain_refund_settled(chain_response: Any) -> bool:
        """True only for a chain answer that proves the refund settled.

        ``success: true`` alone is not proof — the dedup row replays
        ``success: true`` forever, so a response without a refund tx hash
        (absent ``success``, ``success: null``, a proxy error body) must
        not become one (#2814, same hardening as #2813).
        """
        return (
            isinstance(chain_response, dict)
            and chain_response.get("success") is True
            and bool(chain_response.get("refund_tx_hash"))
        )

    def _dedup_replay(self, existing: EscrowRefundRelay | None, *, escrow_refunded: bool) -> dict[str, Any] | None:
        """Stored result for a trustworthy dedup row; None means re-drive.

        A row is replayed as-is only when it carries a tx_hash *and* the
        escrow state still backs it — the node's record reads refunded for
        both pending and confirmed refunds, so a live attempt always
        replays (#2814 double-refund guard). When the escrow proves the
        stored attempt dead (apply-rejected, node record corrected back to
        locked) the row falls through to re-drive (#3008). A hashless row
        falls through for the same reason: on a refunded escrow the caller
        heals it from chain state, on an unrefunded one it is a wedge
        recorded before tx_hash verification and the refund re-drives.
        """
        if existing is not None and existing.tx_hash and escrow_refunded:
            return self._stored_result(existing)
        return None

    def _clear_dead_dedup_hash(self, row: EscrowRefundRelay) -> None:
        """Drop a stored tx_hash the escrow state proved dead (#3008).

        The row stays (job_id dedup + audit trail); only the dead hash is
        cleared so ``_finish_refund``'s heal branch records the replacement
        refund instead of its concurrent-duplicate branch replaying the
        corpse.
        """
        dead = row.tx_hash
        row.tx_hash = None
        self.session.add(row)
        self.session.commit()
        logger.warning(
            "Escrow refund relay cleared dead tx_hash %s for job_id=%s; re-driving the refund",
            dead,
            row.job_id,
        )

    def _fill_dedup_row(self, row: EscrowRefundRelay, *, tx_hash: Any, contract_id: Any) -> None:
        """Heal a dedup row recorded without a tx_hash once the refund verifies."""
        row.tx_hash = tx_hash
        row.contract_id = contract_id
        self.session.add(row)
        self.session.commit()

    async def _record_settled_refund(
        self,
        client_id: str,
        job_id: str,
        escrow: dict[str, Any],
        existing: EscrowRefundRelay | None,
    ) -> dict[str, Any]:
        """Record (or heal) the dedup row for an escrow already refunded on-chain."""
        tx_hash = escrow.get("refund_tx_hash")
        contract_id = escrow.get("contract_id")
        if existing is not None:
            await run_in_threadpool(self._fill_dedup_row, existing, tx_hash=tx_hash, contract_id=contract_id)
            return self._stored_result(existing)
        row = EscrowRefundRelay(client_id=client_id, job_id=job_id, tx_hash=tx_hash, contract_id=contract_id)
        stored = await run_in_threadpool(self._insert_or_existing, row)
        return self._stored_result(stored if stored is not None else row)

    async def _ambiguous_refund_result(
        self,
        client: AsyncAITBCHTTPClient,
        client_id: str,
        job_id: str,
        chain_response: Any,
        existing: EscrowRefundRelay | None,
    ) -> dict[str, Any]:
        """Handle a chain answer that is not a verified settle.

        Re-reads the escrow: if the refund landed anyway (ambiguous
        post-send failure, ``success`` absent), record the dedup row from
        the on-chain state. Otherwise return a retryable failure — no dedup
        row, so the next request re-attempts the chain call (#2814).
        """
        logger.warning(
            "Escrow refund answer not a verified settle: client_id=%s job_id=%s response=%r",
            client_id,
            job_id,
            chain_response,
        )
        escrow_now = await self._fetch_escrow(client, job_id)
        if escrow_now.get("state") == "refunded" or escrow_now.get("refunded_at"):
            return await self._record_settled_refund(client_id, job_id, escrow_now, existing)
        failure: dict[str, Any] = dict(chain_response) if isinstance(chain_response, dict) else {}
        failure["success"] = False
        failure["duplicate"] = False
        return failure

    async def _finish_refund(
        self,
        client: AsyncAITBCHTTPClient,
        client_id: str,
        job_id: str,
        reason: str,
        chain_response: Any,
        existing: EscrowRefundRelay | None,
    ) -> dict[str, Any]:
        """Record the settled refund and shape the relay response.

        Only a verified settle (``success: true`` + refund_tx_hash) records
        the dedup row; anything else re-checks the escrow on-chain or
        returns a retryable failure (#2814).
        """
        if not self._chain_refund_settled(chain_response):
            return await self._ambiguous_refund_result(client, client_id, job_id, chain_response, existing)

        refund_tx_hash = chain_response["refund_tx_hash"]
        contract_id = chain_response.get("contract_id")
        row = EscrowRefundRelay(client_id=client_id, job_id=job_id, tx_hash=refund_tx_hash, contract_id=contract_id)
        stored = await run_in_threadpool(self._insert_or_existing, row)
        if stored is not None:
            if stored.tx_hash:
                # Concurrent identical refund: the row landed first — the chain
                # call may or may not have sealed; return the stored result.
                return self._stored_result(stored)
            # A concurrent wedge row (no tx_hash) won the insert — heal it
            # with the verified hash.
            await run_in_threadpool(self._fill_dedup_row, stored, tx_hash=refund_tx_hash, contract_id=contract_id)
        # Audit: one line per relay — client, job, reason and the tx, never payload detail.
        logger.info(
            "Escrow refund relayed: client_id=%s job_id=%s contract_id=%s refund_tx_hash=%s reason=%s",
            client_id,
            job_id,
            contract_id,
            refund_tx_hash,
            reason,
        )
        result: dict[str, Any] = dict(chain_response)
        result["success"] = True
        result["contract_id"] = contract_id
        result["refund_tx_hash"] = refund_tx_hash
        result["duplicate"] = False
        return result
