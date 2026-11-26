import asyncio
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.payment_escrow import EscrowStatus
from aitbc.rate_limiting import rate_limit

from .. import state
from ..config import settings
from ..models import TaskPayment, TaskSubmission
from ..routing.load_balancer import TaskPriority
from ..services.agent_auth import (
    AgentPrincipal,
    authorize_admin_scope,
    authorize_agent_scope,
    authorize_any_principal,
    authorize_escrow_party,
    optional_agent,
)
from ..services.chain_escrow import (
    EscrowRPCError,
    reconcile_rejected_lock,
    reconcile_rejected_refund,
    reconcile_rejected_release,
)
from ..services.nonce_store import get_nonce_store

logger = get_logger(__name__)
router = APIRouter()

# Resolves the caller's principal if credentials are present, ``None``
# otherwise — the mode-gated gates decide what ``None`` means per endpoint.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]


def _settle_load_balancer_assignment(task_id: str, success: bool, error_message: str | None = None) -> bool:
    """Mark the load-balancer assignment for ``task_id`` terminal (#1749).

    Returns ``True`` when a *pending* assignment was settled. Already-terminal
    or unknown task ids are left alone so a late duplicate report cannot
    double-count metrics. No-op when the balancer is unavailable.
    """
    lb = state.load_balancer
    if lb is None:
        return False
    assignment = lb.get_assignment(task_id)
    if assignment is None or assignment.status != "pending":
        return False
    if success:
        lb.complete_task(task_id, success=True)
    else:
        lb.fail_task(task_id, error_message=error_message)
    return True


def _settle_unpaid_task(task_id: str, principal: AgentPrincipal | None, action: str, success: bool) -> bool:
    """Completion path for tasks that carry no payment escrow (#1749).

    Unpaid submissions never reach the provider-signature checks (there is no
    escrow agent to sign for), so the mode-gated agent-scope check is the auth:
    ``disabled``/``advisory`` keep pre-auth behaviour, ``enforce`` requires a
    principal bound to the assigned agent (admins bypass).
    """
    lb = state.load_balancer
    if lb is None:
        return False
    assignment = lb.get_assignment(task_id)
    if assignment is None or assignment.status != "pending":
        return False
    authorize_agent_scope(principal, assignment.agent_id, action)
    if success:
        lb.complete_task(task_id, success=True)
    else:
        lb.fail_task(task_id, error_message="reported_failed")
    return True


def _lock_escrow_on_chain(escrow: Any, payment: TaskPayment, task_id: str) -> str | None:
    """Anchor ``escrow`` on-chain when the submission carries a lock payload.

    v0.25: a buyer-signed lock_tx settles the escrow on-chain via
    /rpc/escrow/create. Without one there is no lock anchor — and Phase C
    keeps the row PENDING instead of stamping a bookkeeping "locked" with no
    funds behind it: the executor gates work on tx_hash_lock/contract_id, and
    ``locked`` on the record must mean an on-chain anchor exists.

    Returns the ``contract_id`` the chain assigned, or ``None``.
    """
    if state.payment_escrow is None:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    if escrow.status == EscrowStatus.LOCKED:
        # #1553 replay: the escrow for this task already locked on-chain —
        # return its contract id instead of submitting a second lock tx.
        stored_contract_id = escrow.contract_id or escrow.metadata.get("contract_id")
        return stored_contract_id if isinstance(stored_contract_id, str) else None
    submitter = None
    if state.escrow_rpc and (payment.lock_tx or payment.lock_signature):
        from ..services.chain_escrow import make_lock_submitter

        submitter = make_lock_submitter(
            state.escrow_rpc,
            task_id,
            payment.lock_tx,
            payment.lock_signature,
        )
    if submitter is None:
        logger.info(
            "Escrow %s for task %s left PENDING — submission carried no lock anchor",
            escrow.escrow_id,
            task_id,
        )
        return None
    state.payment_escrow.lock(escrow.escrow_id, submitter=submitter)
    contract_id: str | None = submitter.last_response.get("contract_id")  # type: ignore[attr-defined]
    if contract_id:
        # EscrowEntry.contract_id is the store's durable column;
        # keep the metadata mirror for readers and flush both —
        # without persist_entry the mutation dies at restart.
        escrow.contract_id = contract_id
        escrow.metadata["contract_id"] = contract_id
        state.payment_escrow.persist_entry(escrow)
    return contract_id


# The chain's escrow create answers HTTP 425 + Retry-After while the submitted
# ESCROW_LOCK is neither sealed nor visible in the hub mempool — a retryable
# "not confirmed yet", not a rejection. Honour Retry-After when present and
# otherwise back off briefly; only 425 is retried, every other chain error
# still fails the submit immediately.
_LOCK_NOT_CONFIRMED_STATUS = 425
_LOCK_NOT_CONFIRMED_DELAYS = (1.0, 3.0, 5.0)
_LOCK_RETRY_AFTER_CAP_SECONDS = 10.0


def _lock_escrow_on_chain_with_retry(escrow: Any, payment: Any, task_id: str) -> str | None:
    attempts = 1 + len(_LOCK_NOT_CONFIRMED_DELAYS)
    for attempt in range(attempts):
        try:
            return _lock_escrow_on_chain(escrow, payment, task_id)
        except EscrowRPCError as e:
            if e.status_code != _LOCK_NOT_CONFIRMED_STATUS or attempt == attempts - 1:
                raise
            delay = e.retry_after if e.retry_after is not None else _LOCK_NOT_CONFIRMED_DELAYS[attempt]
            delay = min(max(delay, 0.5), _LOCK_RETRY_AFTER_CAP_SECONDS)
            logger.info(
                "Escrow lock for task %s not confirmed yet (HTTP 425); retrying in %.1fs (attempt %d/%d)",
                task_id,
                delay,
                attempt + 2,
                attempts,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def _create_task_escrow(request: TaskSubmission, task_id: str, chain_id: str) -> tuple[str | None, str | None, str | None]:
    """Create the payment escrow for a submission (v0.6.5).

    Returns ``(escrow_id, contract_id, escrow_status)`` — all ``None`` when
    the submission carries no payment or escrow is disabled/unavailable."""
    if not (request.payment and settings.task_payment_escrow_enabled and state.payment_escrow):
        return None, None, None
    # #1553: task_id is the caller-visible natural key — a retry after a lost
    # response must not mint a second escrow and POST a second on-chain lock.
    # Reuse the still-active escrow for this task; a terminal one means this
    # is a genuinely new submission and gets a fresh escrow.
    existing = state.payment_escrow.get_escrow_for_task(task_id)
    if existing is not None and existing.status in (EscrowStatus.PENDING, EscrowStatus.LOCKED):
        # The replay is scoped to identical payment terms: task_id is
        # caller-chosen, so a different requester/agent/amount reusing it must
        # not inherit the first submission's escrow — that would let one
        # buyer's retry key hijack (or be hijacked by) another buyer's
        # payment. Mismatched terms are a conflict, not a replay.
        p = request.payment
        # #2864: timeout_seconds and auto_reinvest_pct are escrow terms too —
        # omitting them let a retry with different terms silently inherit the
        # first submission's escrow. Both are recorded on the entry metadata
        # at create time (auto_reinvest_pct already was; timeout_seconds is
        # new). Entries written before this fix lack the keys and compare as
        # None — a mismatched retry conflicts rather than replaying wrong
        # terms, which is the safe direction for a money path.
        same_terms = (
            existing.requester == p.requester
            and existing.agent == p.agent
            and existing.amount == p.amount
            and existing.fee == p.fee
            and existing.chain_id == chain_id
            and existing.metadata.get("timeout_seconds") == str(p.timeout_seconds)
            and existing.metadata.get("auto_reinvest_pct")
            == (str(p.auto_reinvest_pct) if p.auto_reinvest_pct is not None else None)
        )
        if not same_terms:
            raise ValueError(f"task_id {task_id} already has an active escrow with different payment terms")
        escrow = existing
        # #2955: backfill the payload ref on a replay when the first write
        # predates the proxy — the payload endpoint keys off the entry.
        payload_ref = request.task_data.get("payload_ref")
        if isinstance(payload_ref, str) and "payload_ref" not in escrow.metadata:
            escrow.metadata["payload_ref"] = payload_ref
            state.payment_escrow.persist_entry(escrow)
        # #3005: a reused PENDING entry that reaches the chain lock must
        # prove the durable row first — the same contract the new-entry
        # path enforces below. A first submit whose strict write failed
        # leaves a poisoned in-memory PENDING; without this check a retry
        # would seal a funded escrow with no payment row — the orphan
        # failure #2998 exists to prevent.
        if escrow.status == EscrowStatus.PENDING:
            state.payment_escrow.persist_entry(escrow, strict=True)
    else:
        escrow = state.payment_escrow.create_escrow(
            task_id=task_id,
            chain_id=chain_id,
            requester=request.payment.requester,
            agent=request.payment.agent,
            amount=request.payment.amount,
            fee=request.payment.fee,
            timeout=request.payment.timeout_seconds,
        )
        # #2864: record the full payment terms on the entry so the replay
        # check above can prove identical terms — timeout_seconds joins
        # auto_reinvest_pct here (P2.4/GAP-43: the release path reads
        # auto_reinvest_pct back off the entry and forwards it to the chain;
        # keep it on the entry so it survives a restart between submit and
        # complete — the store serialises metadata).
        escrow.metadata["timeout_seconds"] = str(request.payment.timeout_seconds)
        if request.payment.auto_reinvest_pct is not None:
            escrow.metadata["auto_reinvest_pct"] = str(request.payment.auto_reinvest_pct)
        # #2955: the payload proxy serves the buyer's input CID to the escrow
        # parties; the ref rides the task_data, so pin it to the durable entry.
        payload_ref = request.task_data.get("payload_ref")
        if isinstance(payload_ref, str):
            escrow.metadata["payload_ref"] = payload_ref
        # #2998: the durable row must exist BEFORE the chain lock is
        # submitted — a swallowed store failure here is how a funded escrow
        # ends up with no payment row at all. Strict: a write failure aborts
        # the submit before any on-chain side effect.
        state.payment_escrow.persist_entry(escrow, strict=True)
    contract_id = _lock_escrow_on_chain_with_retry(escrow, request.payment, task_id)
    return escrow.escrow_id, contract_id, escrow.status.value


async def _refund_escrow_after_failed_distribution(task_id: str, escrow_id: str | None) -> None:
    """Expedited refund for an escrow that locked on-chain but whose task
    then failed to distribute (#2865).

    A LOCKED entry means the buyer's funds moved on-chain; leaving it to the
    timeout sweep strands them for the full ``timeout_seconds``. Refund
    immediately through the chain refund path; when that fails (RPC down,
    chain refusing), pull ``expires_at`` to now so the next ``expire_stale``
    sweep refunds promptly instead of after the full timeout. PENDING and
    terminal entries have no on-chain funds to return — a same-task_id
    retry replays or replaces them — so they are left alone. Never raises:
    the distribution error is the one the caller must see.
    """
    if state.payment_escrow is None or escrow_id is None:
        return
    try:
        entry = state.payment_escrow.get_escrow(escrow_id)
        if entry is None or entry.status != EscrowStatus.LOCKED:
            return
        refunded = False
        if state.escrow_rpc is not None:
            from ..services.chain_escrow import make_refund_submitter

            submitter = make_refund_submitter(state.escrow_rpc, task_id, reason="distribution_failed")
            try:
                await asyncio.to_thread(state.payment_escrow.refund, escrow_id, submitter=submitter)
                refunded = True
                logger.warning("Refunded escrow %s for undistributed task %s", escrow_id, task_id)
            except Exception:  # noqa: BLE001 - refund failure falls through to expire-now
                logger.exception(
                    "Immediate refund failed for escrow %s (task %s); expiring for the sweeper",
                    escrow_id,
                    task_id,
                )
        if not refunded:
            # No chain client, or the refund itself failed — expire now so
            # the next expire_stale sweep retries promptly instead of
            # waiting out the full timeout_seconds.
            now = time.time()
            if entry.expires_at is None or entry.expires_at > now:
                entry.expires_at = now
                state.payment_escrow.persist_entry(entry)
                logger.warning(
                    "Escrow %s for undistributed task %s expired early — refund deferred to the sweeper",
                    escrow_id,
                    task_id,
                )
    except Exception:  # noqa: BLE001 - refund containment — never mask the distribution error
        logger.exception("Post-distribution refund path failed for escrow %s (task %s)", escrow_id, task_id)


def _escrow_state_for_task(task_id: str) -> str | None:
    """Best-effort escrow status for logging after a lock failure (#2738)."""
    if state.payment_escrow is None:
        return None
    try:
        entry = state.payment_escrow.get_escrow_for_task(task_id)
    except Exception:  # noqa: BLE001 - log detail only, never masks the 502
        return None
    if entry is None:
        return None
    status_value = getattr(entry.status, "value", entry.status)
    return f"escrow {entry.escrow_id} is {status_value}"


def _reconcile_entry_lock(entry: Any) -> None:
    """Flip a LOCKED entry to REJECTED when its lock tx died on-chain (#2744).

    Best-effort and read-safe: probe failures leave the entry untouched, and
    only a proven ``rejected`` chain record transitions it. Persisted so the
    sweeper and later reads agree.
    """
    if state.payment_escrow is None or not reconcile_rejected_lock(state.escrow_rpc, entry):
        return
    state.payment_escrow.persist_entry(entry)
    logger.warning(
        "Escrow %s lock rejected on-chain for task %s: %s",
        entry.escrow_id,
        entry.task_id,
        entry.metadata.get("lock_rejected_reason"),
    )


def _reconcile_entry_settlement(entry: Any) -> None:
    """Revert a terminal entry whose settle tx died on-chain (#2926).

    RELEASED/REFUNDED are recorded on mempool admission; a proven rejection
    restores LOCKED so the expire sweep and operator views see the funds as
    still held. Best-effort like the lock reconcile: probe failures leave
    the entry untouched.
    """
    if state.payment_escrow is None:
        return
    for reconcile, reason_key in (
        (reconcile_rejected_release, "release_rejected_reason"),
        (reconcile_rejected_refund, "refund_rejected_reason"),
    ):
        if reconcile(state.escrow_rpc, entry):
            state.payment_escrow.persist_entry(entry)
            logger.warning(
                "Escrow %s %s rejected on-chain for task %s: %s",
                entry.escrow_id,
                reason_key.removesuffix("_rejected_reason"),
                entry.task_id,
                entry.metadata.get(reason_key),
            )


@router.post("/tasks/submit")
@rate_limit(rate=50, per=60)
async def submit_task(
    request_http: Request, request: TaskSubmission, background_tasks: BackgroundTasks, principal: OptionalAgent
) -> dict[str, Any]:
    """Submit a task for distribution.

    Phase C: in ``enforce`` mode the call must carry a resolvable credential —
    a buyer agent JWT, ``X-Agent-*`` signed headers or the shared operator key
    (``advisory`` logs ``admin_auth_missing`` and allows; ``disabled`` is a
    no-op). Any resolved principal may submit; payment escrows are bound to
    the buyer by the lock transaction's own signature, not by this check.
    """
    authorize_any_principal(principal, "tasks_submit")
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        try:
            priority = TaskPriority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}") from None

        # v0.6.5: resolve chain_id (defaults to DEFAULT_CHAIN_ID)
        chain_id = request.chain_id or settings.default_chain_id

        task_id = request.task_data.get("task_id", str(uuid.uuid4()))

        # v0.6.5: create payment escrow if payment provided and escrow enabled.
        # #1750: the on-chain lock submitter is a synchronous httpx.Client
        # (up to 15s per call) — run the whole escrow create+lock off the
        # event loop or a slow RPC stalls every endpoint and the websocket.
        try:
            escrow_id, contract_id, escrow_status = await asyncio.to_thread(_create_task_escrow, request, task_id, chain_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Escrow error: {e}") from None
        except Exception:
            # The exception text is the only place the chain error survives now
            # that it no longer goes out in the response, so log the traceback.
            logger.exception("On-chain escrow lock failed for task %s", task_id)
            escrow_state = _escrow_state_for_task(task_id)
            if escrow_state:
                logger.info("Escrow state for task %s after submit lock failure: %s", task_id, escrow_state)
            raise HTTPException(
                status_code=502,
                detail=(
                    "On-chain escrow lock failed; the task was not distributed. "
                    "Retry POST /v1/tasks/submit with the same task_id and payment terms to reconcile."
                ),
            ) from None

        try:
            await state.task_distributor.submit_task(
                request.task_data,
                priority,
                request.requirements,
                chain_id=chain_id,
            )
        except Exception:
            # #2865: the escrow already locked on-chain — a distribution
            # failure must not strand buyer funds until the timeout sweep.
            await _refund_escrow_after_failed_distribution(task_id, escrow_id)
            raise
        return {
            "status": "success",
            "message": "Task submitted successfully",
            "task_id": task_id,
            "chain_id": chain_id,
            "escrow_id": escrow_id,
            "contract_id": contract_id,
            "escrow_status": escrow_status,
            "priority": request.priority,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error submitting task: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/tasks/status")
@rate_limit(rate=200, per=60)
def get_task_status(
    request: Request,
    principal: OptionalAgent,
) -> dict[str, Any]:
    authorize_any_principal(principal, "tasks_status")
    """Get task distribution statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        stats = state.task_distributor.get_distribution_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting task status: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/tasks/queues")
@rate_limit(rate=200, per=60)
def get_queue_sizes(
    request: Request,
    principal: OptionalAgent,
) -> dict[str, Any]:
    authorize_any_principal(principal, "tasks_queues")
    """Get task queue sizes"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        queue_sizes = state.task_distributor.get_queue_sizes()
        return {"status": "success", "queue_sizes": queue_sizes, "timestamp": datetime.now(UTC).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting queue sizes: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/tasks/queues/{priority}/clear")
@rate_limit(rate=50, per=60)
def clear_queue(request: Request, priority: str, principal: OptionalAgent) -> dict[str, Any]:
    """Clear a priority queue.

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "queues_clear")
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        from ..routing.load_balancer import TaskPriority

        try:
            priority_enum = TaskPriority(priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}") from None
        cleared_count = state.task_distributor.clear_queue(priority_enum)
        return {
            "status": "success",
            "message": f"Cleared {cleared_count} tasks from {priority} queue",
            "priority": priority,
            "cleared_count": cleared_count,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing queue: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/tasks/queues/stats")
@rate_limit(rate=200, per=60)
def get_queue_stats(
    request: Request,
    principal: OptionalAgent,
) -> dict[str, Any]:
    authorize_any_principal(principal, "tasks_queues_stats")
    """Get detailed queue statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        queue_sizes = state.task_distributor.get_queue_sizes()
        distribution_stats = state.task_distributor.get_distribution_stats()
        return {
            "status": "success",
            "queue_sizes": queue_sizes,
            "distribution_stats": distribution_stats,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting queue stats: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# ---------------------------------------------------------------------------
# v0.6.5: Payment escrow endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks/escrow/{escrow_id}")
@rate_limit(rate=200, per=60)
def get_escrow_status(
    request: Request,
    principal: OptionalAgent,
    escrow_id: str,
) -> dict[str, Any]:
    authorize_any_principal(principal, "tasks_escrow_status")
    """Get payment escrow status by escrow ID."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow(escrow_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Escrow not found")
    authorize_escrow_party(principal, entry.requester, entry.agent, "tasks_escrow_status")
    _reconcile_entry_lock(entry)
    _reconcile_entry_settlement(entry)
    return {
        "status": "success",
        "escrow": {
            "escrow_id": entry.escrow_id,
            "task_id": entry.task_id,
            "chain_id": entry.chain_id,
            "requester": entry.requester,
            "agent": entry.agent,
            "amount": entry.amount,
            "fee": entry.fee,
            "escrow_status": entry.status.value,
            "tx_hash_lock": entry.tx_hash_lock,
            "tx_hash_release": entry.tx_hash_release,
            "tx_hash_refund": entry.tx_hash_refund,
            "lock_rejected_reason": entry.metadata.get("lock_rejected_reason"),
            "release_rejected_reason": entry.metadata.get("release_rejected_reason"),
            "refund_rejected_reason": entry.metadata.get("refund_rejected_reason"),
            "created_at": entry.created_at,
            "locked_at": entry.locked_at,
            "released_at": entry.released_at,
            "expires_at": entry.expires_at,
            "auto_reinvest_pct": entry.metadata.get("auto_reinvest_pct"),
            "reinvest_status": entry.metadata.get("reinvest_status"),
            "reinvest_stake_id": entry.metadata.get("reinvest_stake_id"),
            "reinvest_amount": entry.metadata.get("reinvest_amount"),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# #2955: party-scoped task payload proxy
#
# The buyer pins its input on its own island daemon and the provider reads it
# through the IPFS swarm. That data plane is best-effort: a provider whose
# bitswap path to the buyer is broken watches its local cat hang to the full
# timeout and the paid task fails. The hub daemon is a public bootstrap
# member the buyer's daemon can reach, so the coordinator can serve the same
# bytes over the authenticated control plane. The ref is pinned to the
# durable escrow entry at submit time; reads are party-scoped like every
# other escrow row read (#1884) and byte-capped like the miner's own cat.
# ---------------------------------------------------------------------------

_PAYLOAD_CID_RE = re.compile(r"[A-Za-z0-9]{1,256}")
_PAYLOAD_PROXY_MAX_ENV = "AGENT_TASK_PAYLOAD_PROXY_MAX_BYTES"
_PAYLOAD_PROXY_DEFAULT_MAX = 512 * 1024 * 1024  # matches the miner-side ffmpeg-sized cap (#801)


def _island_ipfs_api() -> str:
    return os.environ.get("ISLAND_IPFS_API", "http://127.0.0.1:5002")


def _payload_proxy_max_bytes() -> int:
    try:
        return max(1, int(os.environ.get(_PAYLOAD_PROXY_MAX_ENV, _PAYLOAD_PROXY_DEFAULT_MAX)))
    except ValueError:
        return _PAYLOAD_PROXY_DEFAULT_MAX


def _ipfs_dag_total_size(cid: str) -> int | None:
    """Best-effort preflight size via ``dag/stat``; None when unknown.

    Kubo streams NDJSON when the DAG walks several objects — take the maximum
    TotalSize like the miner's own preflight (#2802).
    """
    try:
        resp = requests.post(f"{_island_ipfs_api()}/api/v0/dag/stat", params={"arg": cid}, timeout=30)
        if resp.status_code != 200:
            return None
        total: int | None = None
        for line in resp.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                size = json.loads(line).get("TotalSize")
                size = int(size) if size is not None else None
            except (ValueError, TypeError, AttributeError):
                continue
            if size is not None:
                total = size if total is None else max(total, size)
        return total
    except requests.RequestException as exc:
        logger.debug("payload proxy dag/stat failed for %s: %s", cid, exc)
        return None


def _open_payload_cat(payload_ref: str, cap: int) -> requests.Response:
    """Open the upstream Kubo cat stream, mapping failures to HTTP errors.

    Preflights ``dag/stat`` so an oversized object is refused before any
    bandwidth is spent; the stream itself stays capped downstream because
    the stat is best-effort (None when unknown).
    """
    total = _ipfs_dag_total_size(payload_ref)
    if total is not None and total > cap:
        raise HTTPException(status_code=413, detail=f"payload is {total} bytes, over the {cap} cap")
    try:
        upstream = requests.post(
            f"{_island_ipfs_api()}/api/v0/cat",
            params={"arg": payload_ref},
            timeout=(5, 120),
            stream=True,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"island IPFS unreachable: {e}") from None
    if upstream.status_code == 200:
        return upstream
    try:
        detail = upstream.text[:200]
    except requests.RequestException:
        detail = f"HTTP {upstream.status_code}"
    upstream.close()
    raise HTTPException(status_code=502, detail=f"island IPFS cat failed: {detail}") from None


def _stream_capped(upstream: requests.Response, cap: int):  # noqa: ANN202 - sync generator for StreamingResponse
    """Yield the upstream body with a running byte count; abort over cap.

    The abort truncates the response mid-stream — the consumer's own bounded
    read refuses the partial body rather than executing truncated input.
    Edge case: with an asymmetric config (consumer cap > proxy cap) a
    mid-stream abort is indistinguishable from a legitimately short payload;
    both defaults are the same 512 MiB so the case is inert today — keep the
    two caps aligned when overriding either side.
    """
    received = 0
    try:
        for chunk in upstream.iter_content(1024 * 1024):
            received += len(chunk)
            if received > cap:
                raise ValueError(f"payload exceeds {cap} bytes")
            yield chunk
    finally:
        upstream.close()


@router.get("/tasks/{task_id}/payload")
@rate_limit(rate=60, per=60)
def get_task_payload(
    request: Request,
    principal: OptionalAgent,
    task_id: str,
) -> StreamingResponse:
    """Stream the task's payload CID from the coordinator island daemon.

    Party-or-admin scoped exactly like the escrow row reads: the payload is
    the buyer's paid input, so it must not be enumerable by unrelated
    authenticated principals.
    """
    authorize_any_principal(principal, "tasks_payload")
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Task not found")
    authorize_escrow_party(principal, entry.requester, entry.agent, "tasks_payload")
    payload_ref = entry.metadata.get("payload_ref")
    if not isinstance(payload_ref, str) or not _PAYLOAD_CID_RE.fullmatch(payload_ref):
        raise HTTPException(status_code=404, detail="No payload ref recorded for task")
    cap = _payload_proxy_max_bytes()
    upstream = _open_payload_cat(payload_ref, cap)
    return StreamingResponse(_stream_capped(upstream, cap), media_type="application/octet-stream")


@router.get("/tasks/{task_id}/result")
@rate_limit(rate=60, per=60)
def get_task_result(
    request: Request,
    principal: OptionalAgent,
    task_id: str,
) -> StreamingResponse:
    """Stream the task's result CID from the coordinator island daemon (#2967).

    Symmetric reverse of the payload proxy: the provider pins its result on
    its own island daemon and the buyer reads it through the swarm — the same
    broken-leg data plane, opposite direction. The hub daemon reaches the
    provider fine, so the coordinator can serve the bytes over the
    authenticated control plane. The ref is recorded on the escrow entry by
    the completing provider (never caller-controlled at read time); reads are
    party-scoped and byte-capped exactly like the payload proxy.
    """
    authorize_any_principal(principal, "tasks_result")
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Task not found")
    authorize_escrow_party(principal, entry.requester, entry.agent, "tasks_result")
    result_ref = entry.metadata.get("result_ref")
    if not isinstance(result_ref, str) or not _PAYLOAD_CID_RE.fullmatch(result_ref):
        raise HTTPException(status_code=404, detail="No result ref recorded for task")
    cap = _payload_proxy_max_bytes()
    upstream = _open_payload_cat(result_ref, cap)
    return StreamingResponse(_stream_capped(upstream, cap), media_type="application/octet-stream")


_CALLER_SIG_MAX_SKEW_SECONDS = 300


async def _verify_agent_req_signature(agent: str, action: str, task_id: str, body: dict[str, Any]) -> None:
    """Verify the Phase-B3 ``agent_signature`` (``aitbc-agent-req-v1``) form.

    The claim is ``{"task_id","timestamp","nonce"}`` plus the action's binding
    field — ``amount_units`` for ``complete`` (``or 0`` like the legacy form),
    ``reason`` for ``fail`` when the body carries one. Anything the caller
    asserts in those fields is covered by the signature; a stripped or
    tampered field fails recovery. Timestamp freshness uses the same
    ``agent_msg_max_skew_seconds`` window as ``X-Agent-*`` header auth, and the
    nonce dedups under an ``escrow:<wallet>`` namespace so it cannot collide
    with the ``(agent_id, nonce)`` header dedup — the executor sends the same
    nonce in both places.
    """
    from aitbc.crypto.agent_envelope import recover_request_claim_signer
    from aitbc.crypto.signature_recovery import canonical_address

    timestamp = body.get("timestamp")
    nonce = body.get("nonce")
    if not isinstance(timestamp, str) or not timestamp or not isinstance(nonce, str) or not nonce:
        raise HTTPException(status_code=403, detail="agent_signature requires timestamp + nonce")
    try:
        signed_at = datetime.fromisoformat(timestamp)
        if signed_at.tzinfo is None:
            signed_at = signed_at.replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid timestamp") from None
    if abs((datetime.now(UTC) - signed_at).total_seconds()) > settings.agent_msg_max_skew_seconds:
        raise HTTPException(status_code=403, detail="Stale caller signature")
    claim: dict[str, Any] = {"task_id": task_id, "timestamp": timestamp, "nonce": nonce}
    if action == "complete":
        claim["amount_units"] = body.get("amount_units") or 0
    elif "reason" in body:
        claim["reason"] = body.get("reason")
    recovered = recover_request_claim_signer(claim, body.get("agent_signature"))
    if recovered is None or canonical_address(recovered) != canonical_address(agent):
        raise HTTPException(status_code=403, detail="Caller signature does not match escrow provider")
    if not await get_nonce_store().check_request_nonce(f"escrow:{agent.lower()}", nonce, settings.agent_msg_max_skew_seconds):
        raise HTTPException(status_code=403, detail="nonce_replayed")


async def _require_provider_signature(entry: Any, action: str, task_id: str, body: dict[str, Any]) -> None:
    """Require the caller to prove control of the escrow's provider wallet.

    ``entry.agent`` is the address the escrow pays. Two signature forms are
    accepted — either one must recover to that address:

    * **legacy** (commit ``23ad910d6``): ``signature`` + ``signed_at``, a
      ``recover_signer`` secp256k1 signature over the canonical JSON of
      ``{"action","task_id","signed_at"}`` (plus ``amount_units`` for
      ``complete``).
    * **req-v1** (Phase B3): ``agent_signature`` + ``timestamp`` + ``nonce``,
      over ``{"task_id","timestamp","nonce"[,"amount_units"|"reason"]}`` in the
      ``aitbc-agent-req-v1`` domain — the same domain-separated scheme the
      ``X-Agent-*`` headers use, carried in the body so the signed bytes cover
      the action's own fields.

    Accepting both is the reconciliation choice: the executor emits both forms
    today (B3), the legacy check is the live contract other callers already
    satisfy, and a req-v1-only caller is equally bound to the provider key —
    neither form is weaker than the other, so the endpoint stays caller-bound
    while the fleet migrates.

    Bookkeeping escrows with an empty ``agent`` stay callable unsigned (the
    internal/test path); every escrow with a bound provider requires one of
    the two proofs. Semantics unchanged: ``complete`` and ``fail`` are both
    provider-signed actions — the provider releases its own payment or reports
    its own failure; buyer-side refunds arrive via the timeout sweeper.
    """
    from aitbc.crypto.crypto import recover_signer

    agent = (entry.agent or "").strip()
    if not agent:
        return
    signature = body.get("signature")
    signed_at = body.get("signed_at")
    if isinstance(signature, str) and signature and signed_at is not None:
        try:
            skew = abs(datetime.now(UTC).timestamp() - float(signed_at))
        except (TypeError, ValueError):
            raise HTTPException(status_code=403, detail="Invalid signed_at") from None
        if skew > _CALLER_SIG_MAX_SKEW_SECONDS:
            raise HTTPException(status_code=403, detail="Stale caller signature")
        signed: dict[str, Any] = {"action": action, "task_id": task_id, "signed_at": signed_at}
        if action == "complete":
            signed["amount_units"] = body.get("amount_units") or 0
        recovered = recover_signer(signed, signature)
        if recovered and recovered.lower() == agent.lower():
            return
        raise HTTPException(status_code=403, detail="Caller signature does not match escrow provider")
    if body.get("agent_signature"):
        await _verify_agent_req_signature(agent, action, task_id, body)
        return
    raise HTTPException(
        status_code=403,
        detail="Provider signature required (signature + signed_at, or agent_signature + timestamp + nonce)",
    )


def _record_reinvest_outcome(escrow_mgr: Any, entry: Any, submitter: Any) -> None:
    """Copy the chain's reinvest result onto the escrow entry, then persist it.

    The chain reports what it staked in the release response, which the
    submitter keeps on ``last_response``. Writing it to ``entry.metadata`` is
    what lets the escrow/task views show the outcome after the fact -- the
    entry is the durable record the status endpoints read.
    """
    if submitter is None:
        return
    last = submitter.last_response
    reinvest_stake_id = last.get("reinvest_stake_id")
    reinvest_amount = last.get("reinvest_amount")
    if not (reinvest_stake_id or reinvest_amount):
        return
    if reinvest_stake_id:
        entry.metadata["reinvest_stake_id"] = str(reinvest_stake_id)
    if reinvest_amount:
        entry.metadata["reinvest_amount"] = str(reinvest_amount)
    entry.metadata["reinvest_status"] = "staked" if reinvest_stake_id else "scheduled"
    escrow_mgr.persist_entry(entry)


async def _parse_complete_body(request: Request, entry: Any) -> tuple[int | None, dict[str, Any]]:
    """Parse the optional JSON body of a ``complete`` call.

    Returns ``(amount_units, body)``: ``body`` is the decoded dict (``{}``
    when the body is empty or not a JSON object) for the signature checks,
    and ``amount_units`` the validated partial-billing amount or ``None``.
    """
    amount_units: int | None = None
    body: dict[str, Any] = {}
    raw_body = await request.body()
    if raw_body:
        parsed = json.loads(raw_body)
        if isinstance(parsed, dict):
            body = parsed
            if body.get("amount_units") is not None:
                amount_units = int(body["amount_units"])
                if amount_units <= 0 or amount_units > entry.amount:
                    raise ValueError(f"amount_units must be in (0, {entry.amount}]")
    return amount_units, body


@router.post("/tasks/{task_id}/complete")
@rate_limit(rate=50, per=60)
async def complete_task(request: Request, task_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Mark a task as complete — releases escrow payment to agent (v0.6.5).

    Optional JSON body ``{"amount_units": int}`` bills a partial amount of the
    locked escrow; the unbilled remainder is refunded to the buyer on-chain.
    Requires a signature from the escrow's provider wallet (``entry.agent``)
    over ``{"action","task_id","signed_at","amount_units"}`` — only the party
    that will be paid may release the escrow. The Phase-B3 ``agent_signature``
    (req-v1) form over ``{"task_id","amount_units","timestamp","nonce"}`` is
    accepted equivalently — see ``_require_provider_signature``.

    #1749: tasks without a payment escrow settle the load-balancer assignment
    directly (agent-scope auth); escrow-backed completions also mark the
    assignment complete so ``pending_tasks`` is released.
    """
    escrow_mgr = state.payment_escrow
    entry = escrow_mgr.get_escrow_for_task(task_id) if escrow_mgr else None
    if entry is None:
        if _settle_unpaid_task(task_id, principal, "task_complete", success=True):
            return {
                "status": "success",
                "message": f"Task {task_id} completed",
                "task_id": task_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        if escrow_mgr is None:
            raise HTTPException(status_code=503, detail="Payment escrow not available")
        raise HTTPException(status_code=404, detail="No escrow found for task")
    # A non-None entry can only come from a non-None manager.
    if escrow_mgr is None:  # pragma: no cover - unreachable, narrows for mypy
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    try:
        amount_units, body = await _parse_complete_body(request, entry)
    except (TypeError, ValueError) as e:
        # TypeError: amount_units was a JSON object/array — int() rejects it;
        # without this it escaped as an unhandled 500.
        raise HTTPException(status_code=400, detail=f"Invalid amount_units: {e}") from None
    await _require_provider_signature(entry, "complete", task_id, body)
    # #2967: the completing provider may report the result CID it pinned on
    # its own daemon. Recording it on the durable escrow entry is what lets
    # the result proxy serve buyer-side retrieval when the direct swarm leg
    # is broken. The field is unsigned-but-provider-authenticated — the
    # caller just proved control of the provider wallet, and integrity for
    # the buyer is end-to-end via result_hash regardless. Only the bare-CID
    # shape is stored; anything else is ignored rather than failing the
    # completion itself.
    result_ref = body.get("result_ref")
    if isinstance(result_ref, str) and _PAYLOAD_CID_RE.fullmatch(result_ref):
        entry.metadata["result_ref"] = result_ref
        escrow_mgr.persist_entry(entry)
    try:
        # On-chain release only when the lock actually settled on-chain;
        # bookkeeping-only escrows stay off-chain.
        submitter = None
        if state.escrow_rpc and entry.tx_hash_lock:
            from ..services.chain_escrow import make_release_submitter

            # P2.4/GAP-43: a submission may have asked for a share of the release
            # to be auto-staked for the provider; the chain derives the stake
            # address from the escrow contract, so forwarding the percentage is
            # all this side has to do.
            auto_reinvest_pct = entry.metadata.get("auto_reinvest_pct")
            submitter = make_release_submitter(
                state.escrow_rpc,
                task_id,
                amount_units=amount_units,
                auto_reinvest_pct=float(auto_reinvest_pct) if auto_reinvest_pct is not None else None,
            )
        # #1750: the release submitter is synchronous httpx — off the loop.
        entry = await asyncio.to_thread(escrow_mgr.release, entry.escrow_id, submitter=submitter)
        # The chain reports the reinvestment it performed; record it on the
        # entry so the escrow/task views can show it after the fact.
        _record_reinvest_outcome(escrow_mgr, entry, submitter)
        # #1749: release the load-balancer assignment's pending_tasks slot.
        _settle_load_balancer_assignment(task_id, success=True)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except Exception:
        logger.exception("On-chain escrow release failed for task %s", task_id)
        raise HTTPException(
            status_code=502,
            detail="On-chain escrow release failed; the payment was not released",
        ) from None
    return {
        "status": "success",
        "message": f"Task {task_id} completed, payment released",
        "task_id": task_id,
        "escrow_id": entry.escrow_id,
        "tx_hash_release": entry.tx_hash_release,
        "released_at": datetime.now(UTC).isoformat(),
        "reinvest_status": entry.metadata.get("reinvest_status"),
        "reinvest_stake_id": entry.metadata.get("reinvest_stake_id"),
        "reinvest_amount": entry.metadata.get("reinvest_amount"),
    }


async def _refund_task_escrow(escrow_mgr: Any, entry: Any, task_id: str) -> None:
    """Refund ``entry``'s escrow on-chain, off the event loop (#1750)."""
    submitter = None
    if state.escrow_rpc and entry.tx_hash_lock:
        from ..services.chain_escrow import make_refund_submitter

        submitter = make_refund_submitter(state.escrow_rpc, task_id, reason="task_failed")
    await asyncio.to_thread(escrow_mgr.refund, entry.escrow_id, submitter=submitter)


@router.post("/tasks/{task_id}/fail")
@rate_limit(rate=50, per=60)
async def fail_task(request: Request, task_id: str, principal: OptionalAgent) -> dict[str, Any]:
    """Mark a task as failed — refunds escrow payment to requester (v0.6.5).

    Requires a signature from the escrow's provider wallet over
    ``{"action","task_id","signed_at"}`` — the provider reports its own
    failure; the Phase-B3 ``agent_signature`` (req-v1) form over
    ``{"task_id","reason","timestamp","nonce"}`` is accepted equivalently.
    Buyer-side refunds happen via the escrow timeout sweeper, not
    this endpoint.

    #1749: tasks without a payment escrow settle the load-balancer assignment
    directly (agent-scope auth); escrow-backed failures also fail the
    assignment so ``pending_tasks`` is released.
    """
    escrow_mgr = state.payment_escrow
    entry = escrow_mgr.get_escrow_for_task(task_id) if escrow_mgr else None
    if entry is None:
        if _settle_unpaid_task(task_id, principal, "task_fail", success=False):
            return {
                "status": "success",
                "message": f"Task {task_id} failed",
                "task_id": task_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        if escrow_mgr is None:
            raise HTTPException(status_code=503, detail="Payment escrow not available")
        raise HTTPException(status_code=404, detail="No escrow found for task")
    if escrow_mgr is None:  # pragma: no cover - unreachable, narrows for mypy
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    body: dict[str, Any] = {}
    raw_body = await request.body()
    if raw_body:
        try:
            parsed = json.loads(raw_body)
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}
    await _require_provider_signature(entry, "fail", task_id, body)
    try:
        await _refund_task_escrow(escrow_mgr, entry, task_id)
        # #1749: release the load-balancer assignment's pending_tasks slot.
        _settle_load_balancer_assignment(task_id, success=False, error_message="reported_failed")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except Exception:
        logger.exception("On-chain escrow refund failed for task %s", task_id)
        raise HTTPException(
            status_code=502,
            detail="On-chain escrow refund failed; the payment was not refunded",
        ) from None
    return {
        "status": "success",
        "message": f"Task {task_id} failed, payment refunded",
        "task_id": task_id,
        "escrow_id": entry.escrow_id,
        "tx_hash_refund": entry.tx_hash_refund,
        "refunded_at": datetime.now(UTC).isoformat(),
    }


@router.get("/tasks/{task_id}/escrow")
@rate_limit(rate=200, per=60)
def get_task_escrow(
    request: Request,
    principal: OptionalAgent,
    task_id: str,
) -> dict[str, Any]:
    authorize_any_principal(principal, "tasks_task_escrow")
    """Get the payment escrow for a task (v0.25)."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No escrow found for task")
    authorize_escrow_party(principal, entry.requester, entry.agent, "tasks_task_escrow")
    _reconcile_entry_lock(entry)
    _reconcile_entry_settlement(entry)
    return {
        "status": "success",
        "escrow": {
            "escrow_id": entry.escrow_id,
            "task_id": entry.task_id,
            "chain_id": entry.chain_id,
            "requester": entry.requester,
            "agent": entry.agent,
            "amount": entry.amount,
            "fee": entry.fee,
            "escrow_status": entry.status.value,
            "tx_hash_lock": entry.tx_hash_lock,
            "tx_hash_release": entry.tx_hash_release,
            "tx_hash_refund": entry.tx_hash_refund,
            "lock_rejected_reason": entry.metadata.get("lock_rejected_reason"),
            "release_rejected_reason": entry.metadata.get("release_rejected_reason"),
            "refund_rejected_reason": entry.metadata.get("refund_rejected_reason"),
            "contract_id": entry.contract_id or entry.metadata.get("contract_id"),
            "created_at": entry.created_at,
            "locked_at": entry.locked_at,
            "released_at": entry.released_at,
            "expires_at": entry.expires_at,
            "auto_reinvest_pct": entry.metadata.get("auto_reinvest_pct"),
            "reinvest_status": entry.metadata.get("reinvest_status"),
            "reinvest_stake_id": entry.metadata.get("reinvest_stake_id"),
            "reinvest_amount": entry.metadata.get("reinvest_amount"),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/tasks/escrow-config")
@rate_limit(rate=200, per=60)
def get_escrow_config(
    request: Request,
    principal: OptionalAgent,
) -> dict[str, Any]:
    authorize_any_principal(principal, "tasks_escrow_config")
    """Escrow settlement parameters for buyers (v0.25).

    Returns the node wallet the coordinator settles escrows through, so a
    remote buyer can sign its ESCROW_LOCK to the right custodian without
    knowing the hub's local RPC topology. The address is public on-chain.
    """
    if not state.escrow_rpc:
        raise HTTPException(status_code=503, detail="On-chain escrow not configured")
    wallet = state.escrow_rpc.node_wallet()
    if not wallet:
        raise HTTPException(status_code=502, detail="Could not read settlement wallet from blockchain RPC")
    return {
        "status": "success",
        "settlement_wallet": wallet,
        "chain_id": settings.default_chain_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post("/tasks/escrow/expire-stale")
@rate_limit(rate=10, per=60)
def expire_stale_escrows(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Expire and refund all stale escrows that have passed their timeout (v0.6.5).

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "escrow_expire_stale")
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    from ..lifespan import _escrow_refund_submitter

    expired = state.payment_escrow.expire_stale(refund_submitter_for=_escrow_refund_submitter)
    # #1749: expired escrows mean the task never completed — fail the
    # load-balancer assignment so pending_tasks is released.
    if state.load_balancer is not None:
        for entry in expired:
            state.load_balancer.fail_task(entry.task_id, error_message="escrow_expired")
    return {
        "status": "success",
        "expired_count": len(expired),
        "escrow_ids": [e.escrow_id for e in expired],
        "timestamp": datetime.now(UTC).isoformat(),
    }
