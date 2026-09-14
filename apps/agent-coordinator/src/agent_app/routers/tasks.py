import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from .. import state
from ..config import settings
from ..models import TaskPayment, TaskSubmission
from ..routing.load_balancer import TaskPriority
from ..services.agent_auth import (
    AgentPrincipal,
    authorize_admin_scope,
    authorize_any_principal,
    optional_agent,
)
from ..services.nonce_store import get_nonce_store

logger = get_logger(__name__)
router = APIRouter()

# Resolves the caller's principal if credentials are present, ``None``
# otherwise — the mode-gated gates decide what ``None`` means per endpoint.
OptionalAgent = Annotated[AgentPrincipal | None, Depends(optional_agent)]


def _lock_escrow_on_chain(escrow: Any, payment: TaskPayment, task_id: str) -> str | None:
    """Anchor ``escrow`` on-chain when the submission carries a lock payload.

    v0.25: a buyer-signed lock_tx settles the escrow on-chain via
    /rpc/escrow/create. Without one there is no lock anchor — and Phase C
    keeps the row PENDING instead of stamping a bookkeeping "locked" with no
    funds behind it: the executor gates work on tx_hash_lock/contract_id, and
    ``locked`` on the record must mean an on-chain anchor exists.

    Returns the ``contract_id`` the chain assigned, or ``None``.
    """
    # Only called from _create_task_escrow, which returns early when
    # state.payment_escrow is unset — re-narrow for mypy.
    assert state.payment_escrow is not None
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


def _create_task_escrow(request: TaskSubmission, task_id: str, chain_id: str) -> tuple[str | None, str | None, str | None]:
    """Create the payment escrow for a submission (v0.6.5).

    Returns ``(escrow_id, contract_id, escrow_status)`` — all ``None`` when
    the submission carries no payment or escrow is disabled/unavailable."""
    if not (request.payment and settings.task_payment_escrow_enabled and state.payment_escrow):
        return None, None, None
    escrow = state.payment_escrow.create_escrow(
        task_id=task_id,
        chain_id=chain_id,
        requester=request.payment.requester,
        agent=request.payment.agent,
        amount=request.payment.amount,
        fee=request.payment.fee,
        timeout=request.payment.timeout_seconds,
    )
    contract_id = _lock_escrow_on_chain(escrow, request.payment, task_id)
    return escrow.escrow_id, contract_id, escrow.status.value


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

        # v0.6.5: create payment escrow if payment provided and escrow enabled
        try:
            escrow_id, contract_id, escrow_status = _create_task_escrow(request, task_id, chain_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Escrow error: {e}") from None
        except Exception:
            # The exception text is the only place the chain error survives now
            # that it no longer goes out in the response, so log the traceback.
            logger.exception("On-chain escrow lock failed for task %s", task_id)
            raise HTTPException(
                status_code=502,
                detail="On-chain escrow lock failed; the task was not submitted",
            ) from None

        await state.task_distributor.submit_task(
            request.task_data,
            priority,
            request.requirements,
            chain_id=chain_id,
        )
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
async def get_task_status(request: Request) -> dict[str, Any]:
    """Get task distribution statistics"""
    try:
        if not state.task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        stats = state.task_distributor.get_distribution_stats()
        return {"status": "success", "stats": stats, "timestamp": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error("Error getting task status: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/tasks/queues")
@rate_limit(rate=200, per=60)
async def get_queue_sizes(request: Request) -> dict[str, Any]:
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
async def clear_queue(request: Request, priority: str, principal: OptionalAgent) -> dict[str, Any]:
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
        cleared_count = await state.task_distributor.clear_queue(priority_enum)
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
async def get_queue_stats(request: Request) -> dict[str, Any]:
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
async def get_escrow_status(request: Request, escrow_id: str) -> dict[str, Any]:
    """Get payment escrow status by escrow ID."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow(escrow_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Escrow not found")
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
            "created_at": entry.created_at,
            "locked_at": entry.locked_at,
            "released_at": entry.released_at,
            "expires_at": entry.expires_at,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


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
async def complete_task(request: Request, task_id: str) -> dict[str, Any]:
    """Mark a task as complete — releases escrow payment to agent (v0.6.5).

    Optional JSON body ``{"amount_units": int}`` bills a partial amount of the
    locked escrow; the unbilled remainder is refunded to the buyer on-chain.
    Requires a signature from the escrow's provider wallet (``entry.agent``)
    over ``{"action","task_id","signed_at","amount_units"}`` — only the party
    that will be paid may release the escrow. The Phase-B3 ``agent_signature``
    (req-v1) form over ``{"task_id","amount_units","timestamp","nonce"}`` is
    accepted equivalently — see ``_require_provider_signature``.
    """
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No escrow found for task")
    try:
        amount_units, body = await _parse_complete_body(request, entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid amount_units: {e}") from None
    await _require_provider_signature(entry, "complete", task_id, body)
    try:
        # On-chain release only when the lock actually settled on-chain;
        # bookkeeping-only escrows stay off-chain.
        submitter = None
        if state.escrow_rpc and entry.tx_hash_lock:
            from ..services.chain_escrow import make_release_submitter

            submitter = make_release_submitter(state.escrow_rpc, task_id, amount_units=amount_units)
        state.payment_escrow.release(entry.escrow_id, submitter=submitter)
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
    }


@router.post("/tasks/{task_id}/fail")
@rate_limit(rate=50, per=60)
async def fail_task(request: Request, task_id: str) -> dict[str, Any]:
    """Mark a task as failed — refunds escrow payment to requester (v0.6.5).

    Requires a signature from the escrow's provider wallet over
    ``{"action","task_id","signed_at"}`` — the provider reports its own
    failure; the Phase-B3 ``agent_signature`` (req-v1) form over
    ``{"task_id","reason","timestamp","nonce"}`` is accepted equivalently.
    Buyer-side refunds happen via the escrow timeout sweeper, not
    this endpoint.
    """
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No escrow found for task")
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
        submitter = None
        if state.escrow_rpc and entry.tx_hash_lock:
            from ..services.chain_escrow import make_refund_submitter

            submitter = make_refund_submitter(state.escrow_rpc, task_id, reason="task_failed")
        state.payment_escrow.refund(entry.escrow_id, submitter=submitter)
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
async def get_task_escrow(request: Request, task_id: str) -> dict[str, Any]:
    """Get the payment escrow for a task (v0.25)."""
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    entry = state.payment_escrow.get_escrow_for_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No escrow found for task")
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
            "contract_id": entry.contract_id or entry.metadata.get("contract_id"),
            "created_at": entry.created_at,
            "locked_at": entry.locked_at,
            "released_at": entry.released_at,
            "expires_at": entry.expires_at,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/tasks/escrow-config")
@rate_limit(rate=200, per=60)
async def get_escrow_config(request: Request) -> dict[str, Any]:
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
async def expire_stale_escrows(request: Request, principal: OptionalAgent) -> dict[str, Any]:
    """Expire and refund all stale escrows that have passed their timeout (v0.6.5).

    Phase C admin/operator-only: ``enforce`` → 401 without a principal, 403
    for a non-admin one; ``advisory`` logs and allows; ``disabled`` is a no-op.
    """
    authorize_admin_scope(principal, "escrow_expire_stale")
    if not state.payment_escrow:
        raise HTTPException(status_code=503, detail="Payment escrow not available")
    from ..lifespan import _escrow_refund_submitter

    expired = state.payment_escrow.expire_stale(refund_submitter_for=_escrow_refund_submitter)
    return {
        "status": "success",
        "expired_count": len(expired),
        "escrow_ids": [e.escrow_id for e in expired],
        "timestamp": datetime.now(UTC).isoformat(),
    }
