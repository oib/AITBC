import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ....auth import MinerDep
from ....schemas import AssignedJob, JobFailSubmit, JobResult, JobResultSubmit, JobState, MinerHeartbeat, MinerRegister, PollRequest, Receipt
from ....services import JobService, MinerService
from ....contexts.reputation.services.reputation_service import ReputationService
from ...infrastructure.services.receipts import ReceiptService
from ...zk_applications.services.zk_proofs import zk_proof_service
from ....storage import get_session
from ...tee.attestation import TEEAttestationService

logger = get_logger(__name__)
router = APIRouter(tags=["miner"])

# P2.1: high-value jobs require a ZK receipt proof before escrow release.
# -1 disables the threshold, 0 always requires a proof, default 10 AIT.
_ZK_THRESHOLD_AIT = float(os.getenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", "10"))
_ZK_REQUIRE_PROOF = os.getenv("COORDINATOR_ZK_REQUIRE", "false").lower() == "true"


def _zk_required_for(job: Any) -> bool:
    """Return True if this job's payment triggers the ZK-proof gate."""
    if _ZK_THRESHOLD_AIT < 0:
        return False
    if job.constraints and job.constraints.get("zk_proof_required"):
        return True
    payment_amount = float(job.payment_amount or 0)
    return _ZK_THRESHOLD_AIT == 0 or payment_amount >= _ZK_THRESHOLD_AIT


def _tee_required_for(job: Any) -> bool:
    """Return True if this job requires a TEE attestation."""
    if not job.constraints:
        return False
    return bool(job.constraints.get("tee_attestation_required") or job.constraints.get("tee_enclave_id"))


async def _attach_zk_proof(receipt: dict[str, Any] | None, job: Any, result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Generate and attach a receipt_public Groth16 proof when required."""
    if not receipt:
        return receipt
    if not _zk_required_for(job):
        receipt["zk_status"] = "not_required"
        return receipt
    if not zk_proof_service.is_enabled():
        logger.warning("ZK proof required for job %s but ZK service is not enabled", job.id)
        receipt["zk_status"] = "service_unavailable"
        return receipt
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
        proof = await zk_proof_service.generate_receipt_proof(receipt_model, job_result)
        if not proof:
            logger.error("Failed to generate ZK proof for job %s", job.id)
            receipt["zk_status"] = "generation_failed"
            return receipt
        # Inline verification so the receipt only stores a verified proof.
        verify_result = await zk_proof_service.verify_proof(
            proof["proof"], proof["public_signals"], circuit_name=proof.get("circuit", "receipt_public")
        )
        if not verify_result.get("verified"):
            logger.error("ZK proof did not verify for job %s: %s", job.id, verify_result.get("error"))
            receipt["zk_status"] = f"verification_failed: {verify_result.get('error', 'unknown')}"
            return receipt
        receipt["zk_proof"] = proof
        receipt["zk_status"] = "verified"
        logger.info("ZK receipt proof generated and verified for job %s", job.id)
    except Exception as e:
        logger.error("Error generating ZK proof for job %s: %s", job.id, e)
        receipt["zk_status"] = f"error: {e}"
    return receipt


async def _attach_tee_attestation(
    receipt: dict[str, Any] | None,
    job: Any,
    req: Any,
    session: Any,
) -> dict[str, Any] | None:
    """Verify or store a TEE attestation when the job requires one."""
    if not receipt:
        return receipt
    if not _tee_required_for(job):
        receipt["tee_status"] = "not_required"
        return receipt

    service = TEEAttestationService(session)
    enclave_id = (job.constraints or {}).get("tee_enclave_id") or ""

    try:
        if req.tee_attestation_id:
            attestation = service.get_attestation(req.tee_attestation_id)
            if not attestation:
                receipt["tee_status"] = "attestation_not_found"
            elif attestation.status != "verified":
                receipt["tee_status"] = "attestation_not_verified"
            elif enclave_id and attestation.enclave_id != enclave_id:
                receipt["tee_status"] = "enclave_mismatch"
            else:
                receipt["tee_status"] = "verified"
                receipt["tee_attestation_id"] = attestation.id
        elif req.tee_quote:
            attestation = service.verify_and_store(
                enclave_id or "unknown", req.tee_quote, measurement=enclave_id or ""
            )
            if attestation.status != "verified":
                receipt["tee_status"] = "attestation_rejected"
            elif enclave_id and attestation.measurement and attestation.measurement != enclave_id:
                receipt["tee_status"] = "enclave_mismatch"
            else:
                receipt["tee_status"] = "verified"
                receipt["tee_attestation_id"] = attestation.id
                logger.info("TEE attestation verified for job %s: %s", job.id, attestation.id)
        else:
            logger.warning("TEE attestation required for job %s but none provided", job.id)
            receipt["tee_status"] = "missing"
    except Exception as e:
        logger.error("Error verifying TEE attestation for job %s: %s", job.id, e)
        receipt["tee_status"] = f"error: {e}"

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
    receipt_service = ReceiptService(session)  # type: ignore[arg-type]
    try:
        job = job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
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
    receipt = await _attach_zk_proof(receipt, job, req.result)
    receipt = await _attach_tee_attestation(receipt, job, req, session)
    job.receipt = receipt
    job.receipt_id = receipt["receipt_id"] if receipt else None
    job.completed_at = datetime.now(UTC)
    session.add(job)
    session.commit()
    success = True
    if job.payment_id and job.payment_status == "escrowed":
        from ...payments.services.payments import PaymentService

        payment_service = PaymentService(session)
        # V23-46: release_payment(client_id, job_id, payment_id, reason). This is the
        # miner router, so user["sub"] is the miner -- the owning client is job.client_id,
        # which is what _require_owned_job checks against.
        # P2.2: confidential jobs only release when a verified TEE attestation is present.
        # P2.1: high-value jobs only release when a verified ZK proof is present.
        if _tee_required_for(job):
            tee_status = (receipt or {}).get("tee_status")
            if tee_status != "verified":
                job.error = f"TEE attestation required before escrow release (status: {tee_status})"
                job.state = JobState.failed
                session.commit()
                logger.error(
                    "Escrow release blocked for job %s: TEE status %s", job.id, tee_status
                )
                # v0.14.3: TEE failure now triggers an automatic refund so the
                # customer is not left with an escrowed stuck job.
                refunded = await payment_service.refund_payment(
                    job.client_id, job.id, job.payment_id, reason=f"TEE attestation failed: {tee_status}"
                )
                if refunded:
                    job.payment_status = "refunded"
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
                session.commit()
                success = False
            elif _zk_required_for(job):
                zk_status = (receipt or {}).get("zk_status")
                if zk_status != "verified":
                    job.error = f"ZK proof required before escrow release (status: {zk_status})"
                    session.commit()
                    logger.error(
                        "Escrow release blocked for job %s: ZK status %s", job.id, zk_status
                    )
                    success = False
                else:
                    success = await payment_service.release_payment(
                        job.client_id, job.id, job.payment_id, reason="Job completed successfully"
                    )
            else:
                success = await payment_service.release_payment(
                    job.client_id, job.id, job.payment_id, reason="Job completed successfully"
                )
        elif _zk_required_for(job):
            zk_status = (receipt or {}).get("zk_status")
            if zk_status != "verified":
                job.error = f"ZK proof required before escrow release (status: {zk_status})"
                session.commit()
                logger.error(
                    "Escrow release blocked for job %s: ZK status %s", job.id, zk_status
                )
                success = False
            else:
                success = await payment_service.release_payment(
                    job.client_id, job.id, job.payment_id, reason="Job completed successfully"
                )
        else:
            success = await payment_service.release_payment(
                job.client_id, job.id, job.payment_id, reason="Job completed successfully"
            )
        if success:
            job.payment_status = "released"
            # P2.4: surface reinvestment stake id on the receipt for CLI visibility.
            if receipt is not None and job.payment_id:
                try:
                    from aitbc_shared import JobPayment
                    payment = session.get(JobPayment, job.payment_id)
                    if payment and payment.meta_data:
                        reinvest_stake_id = payment.meta_data.get("reinvest_stake_id")
                        if reinvest_stake_id:
                            receipt_with_reinvest = dict(receipt)
                            receipt_with_reinvest["reinvest_status"] = "staked"
                            receipt_with_reinvest["reinvest_stake_id"] = reinvest_stake_id
                            job.receipt = receipt_with_reinvest
                except Exception as e:
                    logger.warning("Could not attach reinvestment info to receipt: %s", e)
            session.commit()
            logger.info("Auto-released payment %s for completed job %s", job.payment_id, job.id)
        else:
            logger.error("Failed to auto-release payment %s for job %s", job.payment_id, job.id)
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
        service.fail_job(job_id, user["sub"], req.error_message)

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
            "jobs": [service.to_view(job) for job in jobs],
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

        for job in completed_jobs:
            amount = job.payment_amount or Decimal("0")
            token = job.payment_token or "AITBC"
            if job.payment_status == "released":
                paid_earnings += amount
                total_earnings += amount
            elif job.payment_status == "escrowed":
                pending_earnings += amount
            history.append({
                "job_id": job.id,
                "amount": str(amount),
                "currency": token,
                "payment_status": job.payment_status or "unknown",
            })

        return {
            "miner_id": miner_id,
            "total_earnings": float(total_earnings),
            "pending_earnings": float(pending_earnings),
            "paid_earnings": float(paid_earnings),
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
            "total_earnings": 0.0,
            "pending_earnings": 0.0,
            "paid_earnings": 0.0,
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
