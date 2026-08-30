import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import update
from sqlmodel import Session, col, select
from aitbc_shared import JobPayment

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ....auth import MinerDep
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
from ...payments.acceptance import DISPUTED, PENDING_ACCEPTANCE, window_seconds_for
from ....services import JobService, MinerService
from ....contexts.reputation.services.reputation_service import ReputationService
from ...infrastructure.services.receipts import ReceiptService
from ...zk_applications.services.zk_proofs import zk_proof_service
from ...zk_applications.services import model_registry
from ....storage import get_session
from ...tee.attestation import TEEAttestationService, TEEAttestationStatus
from aitbc.tee import AttestationQuote, computation_transcript

logger = get_logger(__name__)
router = APIRouter(tags=["miner"])

# P2.1: high-value jobs require a ZK receipt proof before escrow release.
# -1 disables the threshold, 0 always requires a proof, default 10 AIT.
_ZK_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", "10"))
_ZK_REQUIRE_PROOF = os.getenv("COORDINATOR_ZK_REQUIRE", "false").lower() == "true"

# P2.2: high-value jobs require a TEE attestation quote before escrow release.
# Mirrors the ZK threshold gating above.
_TEE_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_TEE_HIGH_VALUE_THRESHOLD", "10"))
_TEE_REQUIRE = os.getenv("COORDINATOR_TEE_REQUIRE", "false").lower() == "true"


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


def _quote_matches_transcript(quote_b64: str, job: Any, result: dict[str, Any] | None) -> bool:
    """Return True when the quote blob is the SHA-256 of this job's transcript."""
    try:
        quote = AttestationQuote.from_base64(quote_b64)
    except (ValueError, TypeError, KeyError):
        return False
    model_id = model_registry.resolve_model_id(job, result) or ""
    expected = computation_transcript(str(job.id), str(model_id), _job_prompt(job, result), _job_output(result))
    return quote.quote_blob == expected


def _tee_required_for(job: Any, payment_amount: Decimal | None = None) -> bool:
    """Return True if this job requires a TEE attestation.

    A job is TEE-gated when the customer explicitly requested it, when it is
    marked confidential, when it specifies a target enclave or required
    measurement, or when the payment amount crosses the high-value threshold
    (P2.2), mirroring the ZK high-value gating (P2.1).
    """
    if _TEE_REQUIRE:
        return True
    if not job.constraints:
        return _TEE_THRESHOLD_AIT >= 0 and _TEE_THRESHOLD_AIT == 0
    c = job.constraints or {}
    if (
        c.get("tee_attestation_required")
        or c.get("tee_enclave_id")
        or c.get("confidential")
        or c.get("required_enclave_measurement")
    ):
        return True
    if _TEE_THRESHOLD_AIT < 0:
        return False
    if _TEE_THRESHOLD_AIT == 0:
        return True
    return (payment_amount or Decimal("0")) >= _TEE_THRESHOLD_AIT


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
        receipt["zk_status"] = "not_required"
        receipt["computation_correct"] = True
        return receipt
    if not zk_proof_service.is_enabled():
        logger.warning("ZK proof required for job %s but ZK service is not enabled", job.id)
        receipt["zk_status"] = "service_unavailable"
        receipt["computation_correct"] = False
        return receipt

    # Model-execution proof is the Groth16 gate. Unregistered models cannot
    # produce a circuit proof; a registered TEE quote may attest them later.
    model_id = model_registry.resolve_model_id(job, result)
    if not model_id or model_registry.get_model(model_id) is None:
        logger.warning(
            "ZK-required job %s does not specify a supported model (got %r); waiting for TEE attestation",
            job.id,
            model_id,
        )
        receipt["zk_status"] = "unsupported_model"
        receipt["computation_correct"] = False
        return receipt

    try:
        model_proof = await zk_proof_service.generate_model_proof(job, result)
        if not model_proof:
            logger.error("Failed to generate model-execution proof for job %s", job.id)
            receipt["zk_status"] = "generation_failed"
            receipt["computation_correct"] = False
            return receipt

        model = model_registry.get_model(model_id)
        if not model:
            logger.error("No model circuit registered for %s; cannot verify job %s", model_id, job.id)
            receipt["zk_status"] = "unsupported_model"
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
        except Exception as bind_err:
            logger.warning("Receipt binding proof for job %s failed (non-fatal): %s", job.id, bind_err)
            binding_proof = None

        receipt["computation_correct"] = True
        receipt["zk_proof"] = model_proof
        receipt["zk_status"] = "verified"
        if binding_proof:
            receipt["receipt_binding_proof"] = binding_proof
        logger.info("Model-execution proof generated and verified for job %s", job.id)
    except Exception as e:
        logger.error("Error generating ZK proof for job %s: %s", job.id, e)
        receipt["zk_status"] = f"error: {e}"
        receipt["computation_correct"] = False
    return receipt


async def _attach_tee_attestation(
    receipt: dict[str, Any] | None,
    job: Any,
    req: Any,
    session: Any,
    payment_amount: Decimal | None = None,
) -> dict[str, Any] | None:
    """Verify or store a TEE attestation when the job requires one.

    v0.14.4: TEE-gated jobs require a pre-registered, active enclave.
    The coordinator no longer auto-generates self-attested quotes; an
    absent or unregistered quote is a failure and triggers a refund.
    """
    if not receipt:
        return receipt
    model_id = model_registry.resolve_model_id(job, req.result)
    circuitless_zk = _zk_required_for(job, payment_amount) and (not model_id or model_registry.get_model(model_id) is None)
    if not _tee_required_for(job, payment_amount) and not circuitless_zk:
        receipt["tee_status"] = "not_required"
        return receipt

    service = TEEAttestationService(session)
    c = job.constraints or {}
    enclave_id = c.get("tee_enclave_id") or c.get("required_enclave_measurement") or ""
    expected_measurement = c.get("required_enclave_measurement") or enclave_id

    try:
        if req.tee_attestation_id:
            attestation = service.get_attestation(req.tee_attestation_id)
            if not attestation:
                receipt["tee_status"] = "attestation_not_found"
            elif attestation.status != TEEAttestationStatus.VERIFIED.value:
                # v0.14.4: only VERIFIED (registered) attestations count.
                receipt["tee_status"] = "attestation_not_verified"
            elif enclave_id and attestation.enclave_id != enclave_id:
                receipt["tee_status"] = "enclave_mismatch"
            elif expected_measurement and attestation.measurement != expected_measurement:
                receipt["tee_status"] = "measurement_mismatch"
            elif not attestation.registered:
                receipt["tee_status"] = "unregistered_enclave"
            else:
                receipt["tee_status"] = "verified"
                receipt["tee_attestation_id"] = attestation.id
                if not _quote_matches_transcript(attestation.quote, job, req.result):
                    receipt["tee_status"] = "transcript_mismatch"
        elif req.tee_quote:
            if not _quote_matches_transcript(req.tee_quote, job, req.result):
                receipt["tee_status"] = "transcript_mismatch"
                logger.error("TEE quote transcript mismatch for job %s", job.id)
                return receipt
            if not enclave_id:
                try:
                    enclave_id = AttestationQuote.from_base64(req.tee_quote).enclave_id
                    expected_measurement = expected_measurement or enclave_id
                except (ValueError, TypeError, KeyError):
                    enclave_id = "unknown"
            attestation = service.verify_and_store(
                enclave_id or "unknown",
                req.tee_quote,
                measurement=expected_measurement or "",
                require_registered=True,
            )
            if attestation.status == TEEAttestationStatus.VERIFIED.value:
                receipt["tee_status"] = "verified"
                receipt["tee_attestation_id"] = attestation.id
                logger.info("TEE attestation verified for job %s: %s", job.id, attestation.id)
            elif attestation.status == TEEAttestationStatus.SELF_CONSISTENT.value:
                receipt["tee_status"] = "unregistered_enclave"
            else:
                receipt["tee_status"] = "attestation_rejected"
        else:
            receipt["tee_status"] = "tee_quote_missing"
            logger.error("TEE attestation required but no quote supplied for job %s", job.id)
    except Exception as e:
        logger.error("Error verifying TEE attestation for job %s: %s", job.id, e)
        receipt["tee_status"] = f"error: {e}"

    return receipt


def _apply_tee_computation_attestation(
    receipt: dict[str, Any] | None,
    job: Any,
    result: dict[str, Any] | None,
    payment_amount: Decimal | None = None,
) -> dict[str, Any] | None:
    """Allow a registered TEE quote to attest models that have no Groth16 circuit."""
    if not receipt:
        return receipt
    if not _zk_required_for(job, payment_amount):
        return receipt
    if receipt.get("zk_status") == "verified" and receipt.get("computation_correct") is True:
        return receipt
    if receipt.get("tee_status") != "verified":
        return receipt
    model_id = model_registry.resolve_model_id(job, result)
    if model_id and model_registry.get_model(model_id) is not None:
        return receipt
    receipt["zk_status"] = "tee_attested"
    receipt["computation_correct"] = True
    logger.info("TEE-attested computation for unsupported-model job %s", job.id)
    return receipt


@router.post("/miners/register", summary="Register or update miner")
@rate_limit(rate=50, per=60)
async def register(
    req: MinerRegister,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    service = MinerService(session)
    record = service.register(user["sub"], req)
    return {"status": "ok", "session_token": record.session_token}


@router.post("/miners/heartbeat", summary="Send miner heartbeat")
@rate_limit(rate=100, per=60)
async def heartbeat(
    req: MinerHeartbeat,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    try:
        MinerService(session).heartbeat(user["sub"], req)
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
    job = MinerService(session).poll(user["sub"], req.max_wait_seconds)
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return job  # type: ignore[no-any-return]


def _attach_reinvest_info(session: Session, job: Job, receipt: dict[str, Any] | None) -> None:
    """P2.4: surface reinvestment stake id on the receipt for CLI visibility."""
    if receipt is None or not job.payment_id:
        return
    try:
        from aitbc_shared import JobPayment

        payment = session.get(JobPayment, job.payment_id)
        if payment and payment.meta_data:
            reinvest_stake_id = payment.meta_data.get("reinvest_stake_id")
            reinvest_amount = payment.meta_data.get("reinvest_amount")
            if reinvest_stake_id or reinvest_amount:
                receipt_with_reinvest = dict(receipt)
                receipt_with_reinvest["reinvest_status"] = payment.meta_data.get("reinvest_status", "staked")
                if reinvest_stake_id:
                    receipt_with_reinvest["reinvest_stake_id"] = reinvest_stake_id
                if reinvest_amount:
                    receipt_with_reinvest["reinvest_amount"] = reinvest_amount
                job.receipt = receipt_with_reinvest
    except Exception as e:
        logger.warning("Could not attach reinvestment info to receipt: %s", e)


async def _maybe_slash_bond(session: Session, job: Job, condition: str, evidence: str) -> None:
    """G5: slash the miner's bond when a bonded job fails verification."""
    if not (job.constraints and job.constraints.get("bond_required")):
        return
    from ...marketplace.services.bond_slashing import BondSlashingService, SlashingCondition

    await BondSlashingService(session).slash(job, SlashingCondition(condition), evidence)


async def _settle_completed_job(session: Session, payment_service: Any, job: Job, receipt: dict[str, Any] | None) -> bool:
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
            _attach_reinvest_info(session, job, receipt)
            session.add(job)
            session.commit()
            logger.info("Auto-released payment %s for completed job %s", job.payment_id, job.id)
        return bool(released)
    deadline = payment_service.open_acceptance_window(job.id, job.payment_id, window)
    if deadline is None:
        logger.error("Could not hold payment %s for acceptance on job %s", job.payment_id, job.id)
        return False
    job.payment_status = PENDING_ACCEPTANCE
    session.add(job)
    session.commit()
    logger.info(
        "Job %s completed; payment %s held for customer acceptance until %s",
        job.id,
        job.payment_id,
        deadline.isoformat(),
    )
    return True


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
        job = job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    payment = session.get(JobPayment, job.payment_id) if job.payment_id else None
    payment_amount = payment.amount if payment else None
    job.result = req.result
    job.state = JobState.completed
    job.error = None
    metrics = dict(req.metrics or {})
    duration_ms = metrics.get("duration_ms")
    if duration_ms is None and req.result:
        try:
            execution_time = float(req.result.get("execution_time", 0))
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
    receipt = receipt_service.create_receipt(job, user["sub"], req.result, metrics)
    receipt = await _attach_zk_proof(receipt, job, req.result, payment_amount=payment_amount)
    receipt = await _attach_tee_attestation(receipt, job, req, session, payment_amount=payment_amount)
    receipt = _apply_tee_computation_attestation(receipt, job, req.result, payment_amount=payment_amount)
    job.receipt = receipt
    job.receipt_id = receipt["receipt_id"] if receipt else None
    job.completed_at = datetime.now(UTC)
    session.add(job)
    session.commit()
    success = True
    payment = session.get(JobPayment, job.payment_id) if job.payment_id else None
    if payment and payment.status == "escrowed":
        from ...payments.services.payments import PaymentService

        payment_service = PaymentService(session)
        # V23-46: release_payment(client_id, job_id, payment_id, reason). This is the
        # miner router, so user["sub"] is the miner -- the owning client is job.client_id,
        # which is what _require_owned_job checks against.
        # P2.2: confidential jobs only release when a verified TEE attestation is present.
        # P2.1: high-value jobs only release when a verified ZK proof is present.
        if _tee_required_for(job, payment_amount):
            tee_status = (receipt or {}).get("tee_status")
            # "auto_attested" is the coordinator's own self-signed fallback
            # quote (see _attach_tee_attestation) -- no real enclave is
            # involved, so it still clears the release gate (unchanged
            # behavior) but is recorded as distinct from a real quote.
            if tee_status not in {"verified", "auto_attested"}:
                error_message = f"TEE attestation required before escrow release (status: {tee_status})"
                # v0.14.3: force the failure state and error to the database with an
                # explicit update. The ORM object can become stale across the async
                # event loop and PaymentService calls, so SQL is used for the final
                # job-state transition.
                session.execute(
                    update(Job).where(col(Job.id) == job_id).values(state=JobState.failed.value, error=error_message)
                )
                session.commit()
                job.error = error_message
                job.state = JobState.failed
                logger.error("Escrow release blocked for job %s: TEE status %s", job.id, tee_status)
                # v0.14.3: TEE failure now triggers an automatic refund so the
                # customer is not left with an escrowed stuck job.
                refunded = await payment_service.refund_payment(
                    job.client_id, job.id, job.payment_id, reason=f"TEE attestation failed: {tee_status}"
                )
                if refunded:
                    logger.info(
                        "Refunded payment %s for job %s after TEE attestation failure",
                        job.payment_id,
                        job.id,
                    )
                else:
                    logger.error(
                        "Failed to refund payment %s for job %s after TEE attestation failure",
                        job.payment_id,
                        job.id,
                    )
                if refunded:
                    session.execute(update(Job).where(col(Job.id) == job_id).values(payment_status="refunded"))
                    session.commit()
                    job.payment_status = "refunded"
                await _maybe_slash_bond(session, job, "fraud", f"TEE attestation failed: {tee_status}")
                success = False
            elif _zk_required_for(job, payment_amount):
                zk_status = (receipt or {}).get("zk_status")
                if zk_status != "verified":
                    job.error = f"ZK proof required before escrow release (status: {zk_status})"
                    session.commit()
                    logger.error("Escrow release blocked for job %s: ZK status %s", job.id, zk_status)
                    await _maybe_slash_bond(session, job, "bad_result", f"ZK proof failed: {zk_status}")
                    success = False
                else:
                    success = await _settle_completed_job(session, payment_service, job, receipt)
            else:
                success = await _settle_completed_job(session, payment_service, job, receipt)
        elif _zk_required_for(job, payment_amount):
            zk_status = (receipt or {}).get("zk_status")
            if zk_status != "verified":
                job.error = f"ZK proof required before escrow release (status: {zk_status})"
                session.commit()
                logger.error("Escrow release blocked for job %s: ZK status %s", job.id, zk_status)
                await _maybe_slash_bond(session, job, "bad_result", f"ZK proof failed: {zk_status}")
                success = False
            else:
                success = await _settle_completed_job(session, payment_service, job, receipt)
        else:
            success = await _settle_completed_job(session, payment_service, job, receipt)
        if not success:
            logger.error("Failed to settle payment %s for job %s", job.payment_id, job.id)
    miner_service.release(
        user["sub"], success=success, duration_ms=duration_ms, receipt_id=receipt["receipt_id"] if receipt else None
    )

    # Record job completion in the reputation service.
    try:
        from ....contexts.reputation.services.reputation_service import ReputationService

        reputation_service = ReputationService(session)
        earnings = Decimal(str(receipt.get("price", "0"))) if receipt else Decimal("0")
        await reputation_service.record_job_completion(
            agent_id=user["sub"],
            job_id=job_id,
            success=True,
            response_time=float(duration_ms or 0),
            earnings=earnings,
        )
    except Exception as rep_err:
        logger.warning("Failed to record reputation for completed job %s: %s", job_id, rep_err)

    return {"status": "ok", "receipt": receipt}


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
        job = service.fail_job(job_id, user["sub"], req.error_message)

        # G5: a bonded provider that reports a failure has delivered a bad result.
        from ...marketplace.services.bond_slashing import BondSlashingService, SlashingCondition

        if job.constraints and job.constraints.get("bond_required"):
            await BondSlashingService(session).slash(job, SlashingCondition.BAD_RESULT, req.error_message)

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
        except Exception as rep_err:
            logger.warning("Failed to record reputation for failed job %s: %s", job_id, rep_err)

        return {"status": "ok"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None


@router.post("/miners/{miner_id}/jobs", summary="List jobs for a miner")
@rate_limit(rate=200, per=60)
async def list_miner_jobs(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    limit: int = 20,
    offset: int = 0,
    job_type: str | None = None,
    min_reward: Decimal | None = None,
    job_status: str | None = None,
) -> dict[str, Any]:
    """List jobs assigned to a specific miner"""
    try:
        service = JobService(session)
        filters = {}
        if job_type:
            filters["job_type"] = job_type
        if job_status:
            try:
                filters["state"] = JobState(job_status.upper()).value
            except ValueError:
                pass
        jobs = service.list_jobs(assigned_miner_id=miner_id, limit=limit, offset=offset, **filters)
        return {
            "jobs": service.to_views(jobs),
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "miner_id": miner_id,
        }
    except Exception as e:
        logger.error("Error listing miner jobs: %s", e)
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset, "miner_id": miner_id, "error": "Failed to list jobs"}


@router.post("/miners/{miner_id}/earnings", summary="Get miner earnings")
@rate_limit(rate=200, per=60)
async def get_miner_earnings(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    """Get earnings for a specific miner"""
    try:
        from decimal import Decimal
        from ...infrastructure.services.jobs import JobService

        job_service = JobService(session)
        completed_jobs = job_service.list_jobs(
            assigned_miner_id=miner_id,
            state="COMPLETED",
            limit=10000,
            offset=0,
        )

        total_earnings = Decimal("0")
        pending_earnings = Decimal("0")
        paid_earnings = Decimal("0")
        history: list[dict[str, Any]] = []

        payment_ids = [j.payment_id for j in completed_jobs if j.payment_id]
        payments = {}
        if payment_ids:
            payments = {
                p.id: p for p in session.execute(select(JobPayment).where(col(JobPayment.id).in_(payment_ids))).scalars().all()
            }
        for job in completed_jobs:
            payment = payments.get(job.payment_id) if job.payment_id else None
            amount = payment.amount if payment else Decimal("0")
            token = payment.currency if payment else (job.payment_token or "AITBC")
            payment_status = payment.status if payment is not None else (job.payment_status or "unknown")
            if payment_status == "released":
                paid_earnings += amount
                total_earnings += amount
            elif payment_status in {"escrowed", PENDING_ACCEPTANCE, DISPUTED}:
                # G3: money that is locked but not yet paid out, whether it is still
                # running, waiting on the customer, or before an arbiter.
                pending_earnings += amount
            history.append(
                {
                    "job_id": job.id,
                    "amount": str(amount),
                    "currency": token,
                    "payment_status": payment_status,
                }
            )

        return {
            "miner_id": miner_id,
            # Strings, like earnings_history[].amount above: these are Decimal sums
            # of Numeric(20, 8) columns and float() would round them.
            "total_earnings": str(total_earnings),
            "pending_earnings": str(pending_earnings),
            "paid_earnings": str(paid_earnings),
            "completed_jobs": len(completed_jobs),
            "currency": "AITBC",
            "from_time": from_time,
            "to_time": to_time,
            "earnings_history": history[:20],
        }
    except Exception as e:
        logger.error("Error getting miner earnings: %s", e)
        return {
            "miner_id": miner_id,
            "total_earnings": "0",
            "pending_earnings": "0",
            "paid_earnings": "0",
            "completed_jobs": 0,
            "currency": "AITBC",
            "error": str(e),
        }


@router.put("/miners/{miner_id}/capabilities", summary="Update miner capabilities")
@rate_limit(rate=50, per=60)
async def update_miner_capabilities(
    request: Request,
    miner_id: str,
    req: MinerRegister,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    """Update capabilities for a registered miner"""
    try:
        service = MinerService(session)
        record = service.register(user["sub"], req)
        return {
            "miner_id": miner_id,
            "status": "updated",
            "capabilities": req.capabilities,
            "session_token": record.session_token,
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found") from None
    except Exception as e:
        logger.error("Error updating miner capabilities: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.delete("/miners/{miner_id}", summary="Deregister miner")
@rate_limit(rate=50, per=60)
async def deregister_miner(
    request: Request,
    miner_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    """Deregister a miner from the coordinator"""
    try:
        service = MinerService(session)
        service.deregister(miner_id)
        return {"miner_id": miner_id, "status": "deregistered"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="miner not found") from None
    except Exception as e:
        logger.error("Error deregistering miner: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


@router.post("/miners/{miner_id}/jobs/{job_id}/fail", summary="Report job failure")
@rate_limit(rate=50, per=60)
async def fail_job(
    request: Request,
    miner_id: str,
    job_id: str,
    fail_req: JobFailSubmit,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, str]:
    """Report job failure"""
    try:
        job_service = JobService(session)
        job_service.fail_job(job_id, fail_req.error_message)

        # Record the failure in the reputation service.
        try:
            reputation_service = ReputationService(session)
            await reputation_service.record_job_completion(
                agent_id=miner_id,
                job_id=job_id,
                success=False,
                response_time=0.0,
                earnings=Decimal("0"),
            )
        except Exception as rep_err:
            logger.warning("Failed to record reputation for failed job %s: %s", job_id, rep_err)

        return {"job_id": job_id, "status": "failed"}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    except Exception as e:
        logger.error("Error failing job %s: %s", job_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e


class FailJobRequest(BaseModel):
    error_message: str


class CompleteJobRequest(BaseModel):
    output: dict[str, Any]
    receipt: dict[str, Any] | None = None


@router.post("/miners/{miner_id}/jobs/{job_id}/complete", summary="Complete job execution")
@rate_limit(rate=50, per=60)
async def complete_job(
    request: Request,
    miner_id: str,
    job_id: str,
    complete_req: CompleteJobRequest,
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    """
    Complete a job by submitting execution results.

    This endpoint allows miners to submit the results of AI job execution,
    including the output and a verification receipt.
    """
    try:
        job_service = JobService(session)
        result = {"output": complete_req.output, "receipt": complete_req.receipt or {}}
        job = job_service.execute_job(job_id, result)

        # Record completion in the reputation service so dispatch can use it.
        receipt = complete_req.receipt or {}
        output = complete_req.output or {}
        response_time = 0.0
        if "execution_time" in output:
            response_time = float(output["execution_time"]) * 1000.0
        elif receipt.get("started_at") and receipt.get("completed_at"):
            response_time = (float(receipt["completed_at"]) - float(receipt["started_at"])) * 1000.0
        earnings = Decimal(str(receipt.get("price", "0")))
        try:
            reputation_service = ReputationService(session)
            await reputation_service.record_job_completion(
                agent_id=miner_id,
                job_id=job_id,
                success=True,
                response_time=response_time,
                earnings=earnings,
            )
        except Exception as rep_err:
            logger.warning("Failed to record reputation for job %s: %s", job_id, rep_err)

        logger.info(
            "Job %s completed by miner %s",
            job_id,
            miner_id,
            extra={"job_id": job_id, "miner_id": miner_id, "output_size": len(str(complete_req.output))},
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "state": job.state.value,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "receipt_hash": complete_req.receipt.get("hash", "")[:16] if complete_req.receipt else None,
        }
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Error completing job %s: %s", job_id, e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e
