import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, select
from aitbc_shared import JobPayment

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import parse_rate_limit, rate_limit

from ....auth import MinerDep
from ....config import settings
from ....schemas import (
    AssignedJob,
    JobFailSubmit,
    JobResult,
    JobResultSubmit,
    JobState,
    MinerHeartbeat,
    MinerRegister,
    PollRequest,
    Receipt,
)
from ...infrastructure.domain import Job
from ...infrastructure.domain.job_receipt import JobReceipt
from ...payments.acceptance import PENDING_ACCEPTANCE, window_seconds_for
from ....services import JobService, MinerService
from ....contexts.infrastructure.services.spot_check import SpotCheckService
from ...infrastructure.services.receipts import ReceiptService
from ...payments.services.payments import _computation_is_correct
from ...zk_applications.services.zk_proofs import zk_proof_service
from ...zk_applications.services import model_registry
from ....storage import get_session
from .miner_jobs import (
    _MINER_RECEIPT_VERDICT_FIELDS as _MINER_RECEIPT_VERDICT_FIELDS,
    _OPS_ERRORS,
    _strip_miner_receipt_verdicts as _strip_miner_receipt_verdicts,
    router as _miner_jobs_router,
)

logger = get_logger(__name__)
router = APIRouter(tags=["miner"])

# P2.1: high-value jobs require a ZK receipt proof before escrow release.
# -1 disables the threshold, 0 always requires a proof, default 10 AIT.
_ZK_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", "10"))
_ZK_REQUIRE_PROOF = os.getenv("COORDINATOR_ZK_REQUIRE", "false").lower() == "true"


def _zk_required_for(job: Any, payment_amount: Decimal | None = None) -> bool:
    """Return True if this job's payment triggers the ZK-proof gate.

    The gate applies when COORDINATOR_ZK_REQUIRE=true, the job explicitly
    requires a ZK proof, or the payment amount crosses the high-value
    threshold. Whether the requested model actually has a registered circuit
    is decided later in the prover; the gate must not silently downgrade a
    required proof just because the model is missing.
    """
    if _ZK_THRESHOLD_AIT < 0:
        return False
    if _ZK_REQUIRE_PROOF:
        return True
    if job.constraints and job.constraints.get("zk_proof_required"):
        return True
    amount = payment_amount or Decimal("0")
    return _ZK_THRESHOLD_AIT == 0 or amount >= _ZK_THRESHOLD_AIT


def _job_prompt(job: Any, result: dict[str, Any] | None) -> str:
    if job and job.payload:
        return str(job.payload.get("prompt", job.payload.get("input", "")))
    if result:
        return str(result.get("prompt", result.get("input", "")))
    return ""


def _job_output(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    return str(result.get("output") or result.get("result") or result.get("response") or "")


# #2331 tier (a): zk_status values meaning "the miner-reported output for a
# registered circuit model did not match the coordinator-computed output".
# computation_correct is False for all of them, and _settle_escrowed_payment
# refuses escrow release on them even when no ZK proof was required — the
# receipt_model proof commits to the coordinator-computed output, so without
# this check a miner could return arbitrary output and still collect.
_CIRCUIT_OUTPUT_FAILURE_STATUSES = frozenset({"output_mismatch", "output_unparseable", "output_check_error"})


def _parse_circuit_output(raw: Any) -> list[int] | None:
    """Parse a miner-reported circuit output into field elements, or None.

    The post-#2330 miner submits ``json.dumps(output_values)`` — a JSON array
    of field elements — but ``JobSubmitResultBody.output`` also admits a bare
    list, and older miners may send a plain string. Anything that is not a
    list of integers (or digit strings) is unparseable; bools are rejected
    because ``bool`` is an ``int`` subclass.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, list):
        return None
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            return None
        if isinstance(item, int):
            values.append(item)
        elif isinstance(item, str) and item.isdigit():
            values.append(int(item))
        else:
            return None
    return values


def _circuit_output_status(job: Any, result: dict[str, Any] | None, model: Any) -> str | None:
    """Return a zk_status failure string when the reported output is wrong.

    Returns None only when the miner-reported output parses to exactly the
    field array ``model.compute_output`` produces for this job's prompt —
    the same values the receipt_model proof's public ``output_hash`` commits
    to. An unparseable output fails closed (``output_unparseable``): for a
    registered deterministic circuit the coordinator can always compute the
    expected output, so a miner that cannot produce the field array did not
    run the circuit (#2330 contract). A failure to compute the expected
    output itself is ``output_check_error`` — also fail closed, since the
    alternative is attesting an unverifiable computation.
    """
    raw: Any = ""
    if isinstance(result, dict):
        raw = result.get("output") or result.get("result") or result.get("response") or ""
    reported = _parse_circuit_output(raw)
    if reported is None:
        return "output_unparseable"
    try:
        expected = model_registry.expected_output_values(job, model)
    except _OPS_ERRORS:
        logger.exception("Could not compute expected circuit output for job %s", getattr(job, "id", "?"))
        return "output_check_error"
    return None if reported == expected else "output_mismatch"


async def _attach_zk_proof(
    receipt: dict[str, Any] | None,
    job: Any,
    result: dict[str, Any] | None,
    payment_amount: Decimal | None = None,
) -> dict[str, Any] | None:
    """Generate and attach a model-execution proof when required.

    v0.14.4: a high-value/ZK job must prove model execution via a
    ``receipt_model`` Groth16 proof. The ``receipt_public`` proof is still
    generated as a receipt-binding artifact, but it does not set
    ``computation_correct``. ``computation_correct`` is only True when the
    model-execution proof verifies and its public signals match the
    coordinator-derived expected hashes.
    """
    if not receipt:
        return receipt
    if not _zk_required_for(job, payment_amount):
        # #2331 tier (a): a registered circuit model's output is deterministic
        # and cheap to check even when no proof is required — a forged output
        # must not collect just because the job was cheap.
        model_id = model_registry.resolve_model_id(job, result)
        model = model_registry.get_model(model_id) if model_id else None
        if model is not None:
            output_status = _circuit_output_status(job, result, model)
            if output_status is not None:
                logger.error("Circuit output check failed for job %s: %s", job.id, output_status)
                receipt["zk_status"] = output_status
                receipt["computation_correct"] = False
                return receipt
        receipt["zk_status"] = "not_required"
        receipt["computation_correct"] = True
        return receipt
    if not zk_proof_service.is_enabled():
        logger.warning("ZK proof required for job %s but ZK service is not enabled", job.id)
        receipt["zk_status"] = "service_unavailable"
        receipt["computation_correct"] = False
        return receipt

    # Model-execution proof is the Groth16 gate. Unregistered models cannot
    # produce a circuit proof.
    model_id = model_registry.resolve_model_id(job, result)
    if not model_id or model_registry.get_model(model_id) is None:
        logger.warning(
            "ZK-required job %s does not specify a supported model (got %r)",
            job.id,
            model_id,
        )
        receipt["zk_status"] = "unsupported_model"
        receipt["computation_correct"] = False
        return receipt

    return await _attach_model_execution_proof(receipt, job, model_id, result)


async def _attach_model_execution_proof(
    receipt: dict[str, Any],
    job: Any,
    model_id: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    model = model_registry.get_model(model_id)
    if not model:
        logger.error("No model circuit registered for %s; cannot verify job %s", model_id, job.id)
        receipt["zk_status"] = "unsupported_model"
        receipt["computation_correct"] = False
        return receipt

    # #2331 tier (a): the receipt_model proof commits to the
    # coordinator-computed output, so it verifies no matter what the miner
    # returned. Bind the reported output to the expected field array before
    # spending a snarkjs proof on it — a mismatch can never verify anyway.
    output_status = _circuit_output_status(job, result, model)
    if output_status is not None:
        logger.error("Circuit output check failed for job %s: %s", job.id, output_status)
        receipt["zk_status"] = output_status
        receipt["computation_correct"] = False
        return receipt

    try:
        model_proof = await zk_proof_service.generate_model_proof(job, result)
        if not model_proof:
            logger.error("Failed to generate model-execution proof for job %s", job.id)
            receipt["zk_status"] = "generation_failed"
            receipt["computation_correct"] = False
            return receipt

        inputs = model_registry.compute_public_inputs(job, result, model)
        expected_public = model_registry.expected_public_signals(inputs["public_inputs"])

        verify_result = await zk_proof_service.verify_model_proof(
            model_proof["proof"], model_proof["public_signals"], expected_public
        )
        if not verify_result.get("computation_correct"):
            logger.error(
                "Model-execution proof for job %s is not computation_correct: %s",
                job.id,
                verify_result.get("error", "unknown"),
            )
            receipt["zk_status"] = verify_result.get("error") or "computation_incorrect"
            receipt["computation_correct"] = False
            return receipt

        # Optional: also bind the receipt with a receipt_public proof, but do
        # not let it influence computation_correct.
        try:
            receipt_model = Receipt(
                receiptId=receipt.get("receipt_id", ""),
                miner=receipt.get("provider", ""),
                coordinator=receipt.get("coordinator", ""),
                issuedAt=datetime.fromtimestamp(receipt.get("completed_at", 0), tz=UTC),
                status=receipt.get("status", "completed"),
                payload=receipt,
            )
            job_result = JobResult(result=result or {})
            binding_proof = await zk_proof_service.generate_receipt_proof(receipt_model, job_result)
        except _OPS_ERRORS as bind_err:
            logger.warning("Receipt binding proof for job %s failed (non-fatal): %s", job.id, bind_err)
            binding_proof = None

        receipt["computation_correct"] = True
        receipt["zk_proof"] = model_proof
        receipt["zk_status"] = "verified"
        if binding_proof:
            receipt["receipt_binding_proof"] = binding_proof
        logger.info("Model-execution proof generated and verified for job %s", job.id)
    except _OPS_ERRORS as e:
        logger.error("Error generating ZK proof for job %s: %s", job.id, e)
        receipt["zk_status"] = f"error: {e}"
        receipt["computation_correct"] = False
    return receipt


@router.post("/miners/register", summary="Register or update miner")
@rate_limit(*parse_rate_limit(settings.rate_limit_miner_register))
async def register(
    req: MinerRegister,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    service = MinerService(session)
    record = await run_in_threadpool(service.register, user["sub"], req)
    return {"status": "ok", "session_token": record.session_token}


@router.post("/miners/heartbeat", summary="Send miner heartbeat")
@rate_limit(*parse_rate_limit(settings.rate_limit_miner_heartbeat))
async def heartbeat(
    req: MinerHeartbeat,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    try:
        await run_in_threadpool(MinerService(session).heartbeat, user["sub"], req)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not registered") from None
    return {"status": "ok"}


@router.post("/miners/poll", response_model=AssignedJob, summary="Poll for next job")
@rate_limit(rate=100, per=60)
async def poll(
    request: Request,
    req: PollRequest,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> AssignedJob | Response:
    try:
        job = await run_in_threadpool(MinerService(session).poll, user["sub"], req.max_wait_seconds)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not registered") from None
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job  # type: ignore[no-any-return]


async def _maybe_slash_bond(session: Session, job: Job, condition: str, evidence: str) -> None:
    """G5: slash the miner's bond when a bonded job fails verification."""
    if not (job.constraints and job.constraints.get("bond_required")):
        return
    from ...market.services.bond_slashing import BondSlashingService, SlashingCondition

    await BondSlashingService(session).slash(job, SlashingCondition(condition), evidence)


async def _retry_completed_settlement(session: Session, job: Job) -> dict[str, Any]:
    """#1800: idempotent settlement retry for an already-completed job.

    ``submit_result`` marks the job COMPLETED before the money moves and
    ``release_payment`` requires that terminal state, so a failed settle
    legitimately leaves COMPLETED + escrowed — a row the SettlementReconciler
    already scans for. This gives the assigned miner the same retry on
    demand: only the money movement is re-attempted; the receipt, metrics and
    proof work are not repeated, so resubmits cannot accumulate
    JobReceipt rows or double-settle (the payment CAS from #1797 arbitrates).
    """
    from ...payments.services.payments import PaymentService

    if await _settle_completed_job(session, PaymentService(session), job):
        return {"status": "ok", "receipt": job.receipt, "settlement": "settled"}
    return {"status": "settlement_pending", "receipt": job.receipt}


async def _settle_completed_job(session: Session, payment_service: Any, job: Job) -> bool:
    """Open the customer's acceptance window, or pay the provider now (G3).

    Releasing inside this request made the provider the only party to the settlement:
    whatever it submitted was accepted by the act of submitting it. With a window
    configured the escrow instead stays locked until the customer accepts, the
    customer rejects, or the window expires and the sweeper releases it.

    A window of zero restores same-request settlement for deployments that depend on
    it. Either way the caller gets True only if the payment is in a state it can
    settle from, so a miner is never told the job succeeded when the money did not
    move and is not waiting.
    """
    window = window_seconds_for(job.constraints)
    if window <= 0:
        released = await payment_service.release_payment(
            job.client_id, job.id, job.payment_id, reason="Job completed successfully"
        )
        if released:
            job.payment_status = "released"
            session.add(job)
            session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
            logger.info("Auto-released payment %s for completed job %s", job.payment_id, job.id)
            return True
        return False
    deadline = payment_service.open_acceptance_window(job.id, job.payment_id, window)
    if deadline is None:
        logger.error("Could not hold payment %s for acceptance on job %s", job.payment_id, job.id)
        return False
    job.payment_status = PENDING_ACCEPTANCE
    session.add(job)
    session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
    logger.info(
        "Job %s completed; payment %s held for customer acceptance until %s",
        job.id,
        job.payment_id,
        deadline.isoformat(),
    )
    return True


def _is_shadow_mode(job: Job) -> bool:
    """Return True if this job is a shadow-mode spot-check re-run."""
    return bool((job.constraints or {}).get("shadow_mode")) or bool((job.constraints or {}).get("spot_check_for"))


def _resolve_duration_ms(req: JobResultSubmit, metrics: dict[str, Any], job: Job, job_id: str) -> int | None:
    duration_ms = metrics.get("duration_ms")
    if duration_ms is None:
        try:
            execution_time = float(req.result.execution_time or 0)
            if execution_time > 0:
                duration_ms = int(execution_time * 1000)
                metrics["duration_ms"] = duration_ms
        except (TypeError, ValueError):
            pass
    if duration_ms is None and job.requested_at:
        now = datetime.now(UTC)
        requested_at = job.requested_at if job.requested_at.tzinfo else job.requested_at.replace(tzinfo=UTC)
        duration_ms = int((now - requested_at).total_seconds() * 1000)
        if duration_ms < 0:
            logger.warning("Computed negative duration_ms for job %s; setting to 0", job_id)
            duration_ms = 0
        metrics["duration_ms"] = duration_ms
    if duration_ms is not None:
        duration_ms = int(duration_ms)
    return duration_ms


async def _zk_gate_failure(session: Session, job: Job, zk_status: Any) -> None:
    job.error = f"ZK proof required before escrow release (status: {zk_status})"
    session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
    logger.error("Escrow release blocked for job %s: ZK status %s", job.id, zk_status)
    await _maybe_slash_bond(session, job, "bad_result", f"ZK proof failed: {zk_status}")


async def _settle_escrowed_payment(
    session: Session,
    job: Job,
    payment_amount: Decimal | None,
    receipt: dict[str, Any] | None,
    job_id: str,
) -> bool:
    from ...payments.services.payments import PaymentService

    payment_service = PaymentService(session)
    success = True
    # V23-46: release_payment(client_id, job_id, payment_id, reason). This is the
    # miner router, so user["sub"] is the miner -- the owning client is job.client_id,
    # which is what _require_owned_job checks against.
    # P2.1: high-value jobs only release when a verified ZK proof is present.
    # #2331 tier (a): a registered circuit model whose reported output failed
    # the coordinator-side equality check never releases escrow, gated or
    # not — the same failure surface as a failed ZK proof.
    # #2375: the TEE attestation gate is removed — no enclave hardware
    # exists on the fleet; high-value jobs are governed by the ZK rail alone.
    output_status = (receipt or {}).get("zk_status")
    if output_status in _CIRCUIT_OUTPUT_FAILURE_STATUSES:
        await _zk_gate_failure(session, job, output_status)
        success = False
    elif _zk_required_for(job, payment_amount) and not _computation_is_correct(receipt, job):
        await _zk_gate_failure(session, job, (receipt or {}).get("zk_status"))
        success = False
    else:
        success = await _settle_completed_job(session, payment_service, job)
    if not success:
        logger.error("Failed to settle payment %s for job %s", job.payment_id, job.id)
    return success


async def _sync_receipt_row(session: Session, job: Job, receipt: dict[str, Any] | None) -> None:
    if job.receipt_id and receipt:
        receipt_row = await run_in_threadpool(
            lambda: session.execute(select(JobReceipt).where(JobReceipt.receipt_id == job.receipt_id)).scalars().first()
        )
        if receipt_row:
            receipt_row.payload = receipt
            session.add(receipt_row)
            await run_in_threadpool(session.commit)


async def _finalize_result_response(
    session: Session,
    job: Job,
    job_id: str,
    miner_sub: str,
    duration_ms: int | None,
    receipt: dict[str, Any] | None,
    is_shadow: bool,
    spot_check_record: dict[str, Any] | None,
) -> dict[str, Any]:
    # For deterministic-decoding jobs that are not themselves spot-checks,
    # schedule a shadow re-run. This is log-only and does not block settlement.
    if not is_shadow:
        try:
            await run_in_threadpool(SpotCheckService(session).schedule_if_eligible, job)
        except _OPS_ERRORS as spot_err:
            logger.warning("Failed to schedule spot-check for job %s: %s", job_id, spot_err)

    # Record job completion in the reputation service.
    if is_shadow:
        return {"status": "ok", "receipt": receipt, "spot_check": spot_check_record or {}}

    try:
        from ....contexts.reputation.services.reputation_service import ReputationService

        reputation_service = ReputationService(session)
        earnings = Decimal(str(receipt.get("price", "0"))) if receipt else Decimal("0")
        await reputation_service.record_job_completion(
            agent_id=miner_sub,
            job_id=job_id,
            success=True,
            response_time=float(duration_ms or 0),
            earnings=earnings,
        )
    except _OPS_ERRORS as rep_err:
        logger.warning("Failed to record reputation for completed job %s: %s", job_id, rep_err)

    return {"status": "ok", "receipt": receipt}


async def _submit_failed_result(
    session: Session,
    job: Job,
    job_id: str,
    miner_sub: str,
    req: JobResultSubmit,
    miner_service: MinerService,
) -> dict[str, Any]:
    """Route a miner-reported execution failure submitted via /result (#2242).

    ``production_miner._submit_failure`` posts ``result.status="failed"`` to
    this endpoint instead of ``/miners/{job_id}/fail``, so the result handler
    must branch on it. Mirrors ``submit_failure``: the job goes FAILED with
    the miner's error, reputation records a failure, and the miner slot is
    released — but no receipt is issued, no settlement is attempted, and
    ``job.result`` stays unset so the escrowed payment remains refundable by
    the customer (``refund_payment`` treats an undelivered escrowed payment as
    refundable, and the escrow refund relay accepts FAILED as a terminal-unpaid
    state). A self-reported failure never slashes the bond (#2278): it proves
    nothing about the provider and the customer picks the input that made it
    fail. Bond slashes stay on verified faults — FRAUD on an operator-ruled
    refund, the ZK gate, and the downtime sweeper.
    """
    metrics = req.metrics.model_dump(mode="json", exclude_none=True)
    duration_ms = _resolve_duration_ms(req, metrics, job, job_id)
    error_message = req.result.error or "miner reported job failure"
    job.state = JobState.failed
    job.error = error_message
    session.add(job)
    session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
    try:
        from ....contexts.reputation.services.reputation_service import ReputationService

        reputation_service = ReputationService(session)
        await reputation_service.record_job_completion(
            agent_id=miner_sub,
            job_id=job_id,
            success=False,
            response_time=float(duration_ms or 0),
            earnings=Decimal("0"),
        )
    except _OPS_ERRORS as rep_err:
        logger.warning("Failed to record reputation for failed job %s: %s", job_id, rep_err)
    await run_in_threadpool(
        miner_service.release,
        miner_sub,
        success=False,
        duration_ms=duration_ms,
        receipt_id=None,
    )
    logger.info("Job %s marked FAILED from miner-reported result status", job_id)
    return {"status": "ok", "receipt": None, "job_state": JobState.failed.value}


@router.post("/miners/{job_id}/result", summary="Submit job result")
@rate_limit(rate=50, per=60)
async def submit_result(
    request: Request,
    job_id: str,
    req: JobResultSubmit,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    job_service = JobService(session)
    miner_service = MinerService(session)
    receipt_service = ReceiptService(session)
    try:
        job = await run_in_threadpool(job_service.get_job, job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    # Only the assigned miner may deliver a result, and only while the job is
    # running — otherwise any miner could overwrite another provider's work
    # (or a finished job) and have the receipt issued in their own name.
    if job.assigned_miner_id != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job is assigned to a different miner")
    if job.state != JobState.running:
        # #1800: a job that completed but whose settlement failed keeps its
        # escrow — answer a resubmit with a settlement retry instead of a
        # permanent 409. The gate is deliberately narrow: only COMPLETED with
        # the payment still escrowed. pending_acceptance/disputed payments are
        # already inside the customer acceptance flow and must not be
        # re-settled here; every other state is a real conflict.
        if job.state == JobState.completed and job.payment_id:
            held = await run_in_threadpool(session.get, JobPayment, job.payment_id)
            if held is not None and held.status == "escrowed":
                return await _retry_completed_settlement(session, job)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"job is {job.state}, not running")
    # #2242: a miner may report execution failure through this endpoint too
    # (production_miner._submit_failure posts result.status="failed" here
    # rather than calling /fail). Route it to the failure path — a failed
    # result must never mark the job COMPLETED, issue a receipt, or hold the
    # escrow in pending_acceptance.
    if (req.result.status or "").strip().lower() == "failed":
        return await _submit_failed_result(session, job, job_id, user["sub"], req, miner_service)
    payment = await run_in_threadpool(session.get, JobPayment, job.payment_id) if job.payment_id else None
    payment_amount = payment.amount if payment else None
    is_shadow = _is_shadow_mode(job)
    result_payload = req.result.model_dump(mode="json", exclude_none=True)
    metrics = req.metrics.model_dump(mode="json", exclude_none=True)
    job.result = result_payload
    job.state = JobState.completed
    job.error = None
    duration_ms = _resolve_duration_ms(req, metrics, job, job_id)
    receipt = await run_in_threadpool(receipt_service.create_receipt, job, user["sub"], result_payload, metrics)
    receipt = await _attach_zk_proof(receipt, job, result_payload, payment_amount=payment_amount)
    if receipt:
        receipt = await run_in_threadpool(receipt_service.sign_receipt, receipt)
    job.receipt = receipt
    job.receipt_id = receipt["receipt_id"] if receipt else None
    job.completed_at = datetime.now(UTC)
    session.add(job)
    session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
    # Keep the JobReceipt row in sync with the final receipt (after ZK
    # attachments) so downstream consumers use the authoritative payload.
    await _sync_receipt_row(session, job, receipt)
    success = True
    payment = await run_in_threadpool(session.get, JobPayment, job.payment_id) if job.payment_id else None
    spot_check_record: dict[str, Any] | None = None
    if is_shadow:
        spot_check_record = await run_in_threadpool(SpotCheckService(session).complete_spot_check, job)
    elif payment and payment.status == "escrowed":
        success = await _settle_escrowed_payment(session, job, payment_amount, receipt, job_id)
    await run_in_threadpool(
        miner_service.release,
        user["sub"],
        success=success,
        duration_ms=duration_ms,
        receipt_id=receipt["receipt_id"] if receipt else None,
    )

    return await _finalize_result_response(
        session, job, job_id, user["sub"], duration_ms, receipt, is_shadow, spot_check_record
    )


@router.post("/miners/{job_id}/fail", summary="Submit job failure")
@rate_limit(rate=50, per=60)
async def submit_failure(
    request: Request,
    job_id: str,
    req: JobFailSubmit,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    try:
        service = JobService(session)
        await run_in_threadpool(service.fail_job, job_id, user["sub"], req.error_message)

        # #2278: no bond slash here. A miner-reported failure is unverified and
        # the customer chooses the input, so slashing on it let a customer burn
        # a provider's bond for free (the escrow stays refundable). Verified
        # faults still slash: FRAUD on an operator-ruled refund, the ZK gate
        # and the downtime sweeper.

        # Record the failure in the reputation service.
        try:
            from ....contexts.reputation.services.reputation_service import ReputationService

            reputation_service = ReputationService(session)
            await reputation_service.record_job_completion(
                agent_id=user["sub"],
                job_id=job_id,
                success=False,
                response_time=0.0,
                earnings=Decimal("0"),
            )
        except _OPS_ERRORS as rep_err:
            logger.warning("Failed to record reputation for failed job %s: %s", job_id, rep_err)

        return {"status": "ok"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None


router.include_router(_miner_jobs_router)
