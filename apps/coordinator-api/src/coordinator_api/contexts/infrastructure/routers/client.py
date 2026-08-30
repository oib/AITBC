from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc_shared import JobPayment
from aitbc.rate_limiting import rate_limit

from ....auth import ClientDep
from ....config import settings
from ...marketplace.offer_quote import OfferLookupFailed, OfferQuote, OfferUnavailable, resolve_offer
from ...payments.acceptance import PENDING_ACCEPTANCE
from ...payments.provider_binding import same_address
from ...payments.services.payments import PaymentService, _zk_required_for_payment
from ....custom_types import JobState
from ....schemas import JobCreate, JobPaymentCreate, JobRejection, JobResult, JobView
from ....services import JobService
from ....storage import get_session
from ....utils.cache import cached, get_cache_config

logger = get_logger(__name__)
router = APIRouter(tags=["client"])

# G1: whether a priced job must name the offer it was bought against. Off by default
# because the GPU purchase path and existing clients still price jobs directly; an
# operator who wants every paid job to trace back to a published quote turns it on.
_OFFER_REQUIRE = os.getenv("COORDINATOR_REQUIRE_OFFER", "false").lower() == "true"


async def _apply_offer_quote(req: JobCreate) -> tuple[JobCreate, OfferQuote | None]:
    """Bind a submission to the marketplace offer it names, or leave it untouched.

    Returns the request to actually submit -- its price and payee taken from the offer
    -- along with the quote, which the payment records so a settlement can later be
    checked against what was advertised.

    This runs before the job is created, so a submission that disagrees with the offer
    is refused outright rather than leaving a queued job behind it.

    Raises:
        HTTPException: 400 when the offer cannot be bought or the submission
            contradicts it, 503 when the offer registry could not be asked.
    """
    if not req.offer_id:
        if _OFFER_REQUIRE and req.payment_amount and req.payment_amount > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="a priced job must name the offer_id it was bought against",
            )
        return req, None

    try:
        quote = await resolve_offer(req.offer_id, req.offer_quantity)
    except OfferUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OfferLookupFailed as exc:
        logger.warning("Offer %s could not be resolved: %s", req.offer_id, exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    # The offer decides who is paid. A caller may still name a provider, but only to
    # say the same thing: silently preferring the offer would hide a client bug whose
    # end state is money locked to the wrong wallet.
    if req.provider_address and not same_address(req.provider_address, quote.provider_address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"provider_address {req.provider_address} disagrees with offer "
                f"{quote.offer_id}, which is sold by {quote.provider_address}"
            ),
        )

    # And the offer decides the price. Under-funding leaves the provider short; over-
    # funding is no kindness either, because release pays out the whole escrow.
    if req.payment_amount is not None and req.payment_amount != quote.total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"payment_amount {req.payment_amount} does not match the quote for offer {quote.offer_id}: {quote.describe()}"
            ),
        )

    logger.info("Job priced against offer %s: %s payable to %s", quote.offer_id, quote.describe(), quote.provider_address)
    return req.model_copy(update={"payment_amount": quote.total, "provider_address": quote.provider_address}), quote


@router.post("/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED, summary="Submit a job")
@rate_limit(rate=50, per=60)
async def submit_job(
    req: JobCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobView:
    req, quote = await _apply_offer_quote(req)
    service = JobService(session)
    job = service.create_job(user["sub"], req)
    if req.payment_amount and req.payment_amount > 0:
        if req.buyer_lock_signature:
            # One-step submission: the client has already signed the ESCROW_LOCK tx.
            try:
                payment_service = PaymentService(session)
                payment_create = JobPaymentCreate(
                    job_id=job.id,
                    amount=req.payment_amount,
                    currency=req.payment_currency,
                    payment_method="aitbc_token",
                    buyer_address=req.buyer_address,
                    provider_address=req.provider_address,
                    buyer_lock_signature=req.buyer_lock_signature,
                    buyer_lock_nonce=req.buyer_lock_nonce,
                    buyer_lock_fee=req.buyer_lock_fee,
                    auto_reinvest_pct=req.constraints.auto_reinvest_pct if req.constraints else None,
                    offer_id=quote.offer_id if quote else None,
                    offer_unit_price=quote.unit_price if quote else None,
                    offer_price_unit=quote.price_unit if quote else None,
                    offer_quantity=quote.quantity if quote else None,
                )
                # V23-46: create_payment(client_id, job_id, payment_data). Passing (job.id,
                # payment_create) made client_id=job.id, job_id=payment_create, and left
                # payment_data unfilled -- a TypeError, swallowed by the except below.
                payment = await payment_service.create_payment(user["sub"], job.id, payment_create)
                job.payment_id = payment.id
                job.payment_status = payment.status
                session.commit()
                session.refresh(job)
                logger.info("Payment created for job %s: %s", job.id, payment.id)
            except Exception as e:
                # Rollback any partial payment changes before marking as skipped.
                # This prevents orphaned payment records from a partially-successful create_payment.
                session.rollback()
                session.refresh(job)
                # The job is still created so the client can retry the escrow against it,
                # but it will not be dispatched while payment_status is "skipped" (G4).
                logger.warning(
                    "Payment creation failed for job %s; it will not be dispatched until payment is secured: %s",
                    job.id,
                    e,
                )
                job.payment_status = "skipped"
                session.commit()
                session.refresh(job)
        else:
            # Two-step submission: the job is created with quoted terms but no escrow yet.
            # The client must call POST /v1/payments with a signed ESCROW_LOCK to secure it.
            logger.info(
                "Job %s created without escrow lock; call POST /v1/payments with buyer_lock_signature to dispatch",
                job.id,
            )
    return service.to_view(job)  # type: ignore[no-any-return]


@router.get("/jobs/{job_id}", response_model=JobView, summary="Get job status")
@rate_limit(rate=200, per=60)
async def get_job(
    request: Request,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobView:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=user["sub"])
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    return service.to_view(job)  # type: ignore[no-any-return]


@router.get("/jobs/{job_id}/result", response_model=JobResult, summary="Get job result")
@rate_limit(rate=200, per=60)
async def get_job_result(
    request: Request,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobResult:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=user["sub"])
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    if job.state not in {JobState.completed, JobState.failed, JobState.canceled, JobState.expired}:
        raise HTTPException(status_code=status.HTTP_425_TOO_EARLY, detail="job not ready") from None
    if job.result is None and job.receipt is None:
        raise HTTPException(status_code=status.HTTP_425_TOO_EARLY, detail="job not ready") from None
    return service.to_result(job)  # type: ignore[no-any-return]


@router.post("/jobs/{job_id}/cancel", response_model=JobView, summary="Cancel job")
@rate_limit(rate=50, per=60)
async def cancel_job(
    request: Request,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobView:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=user["sub"])
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    if job.state not in {JobState.queued, JobState.running}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job not cancelable") from None
    job = service.cancel_job(job)
    return service.to_view(job)  # type: ignore[no-any-return]


@router.get("/jobs/{job_id}/receipt", summary="Get latest signed receipt")
@rate_limit(rate=200, per=60)
async def get_job_receipt(
    request: Request,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> dict:
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=user["sub"])
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    if not job.receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="receipt not available") from None
    return job.receipt  # type: ignore[no-any-return]


@router.get("/jobs/{job_id}/receipts", summary="List signed receipts")
@rate_limit(rate=200, per=60)
async def list_job_receipts(
    request: Request,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> dict:
    service = JobService(session)
    receipts = service.list_receipts(job_id, client_id=user["sub"])
    return {"items": [row.payload for row in receipts]}


@router.get("/jobs", summary="List jobs with filtering")
@rate_limit(rate=200, per=60)
@cached(**get_cache_config("job_list"))
async def list_jobs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    job_type: str | None = None,
) -> dict:
    """List jobs with optional filtering by status and type"""
    service = JobService(session)
    filters = {}
    if status:
        try:
            filters["state"] = JobState(status.upper())
        except ValueError:
            pass
    if job_type:
        filters["job_type"] = job_type  # type: ignore[assignment]
    jobs = service.list_jobs(client_id=user["sub"], limit=limit, offset=offset, **filters)
    return {"items": service.to_views(jobs), "total": len(jobs), "limit": limit, "offset": offset}


@router.get("/jobs/history", summary="Get job history")
@rate_limit(rate=200, per=60)
@cached(**get_cache_config("job_list"))
async def get_job_history(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    job_type: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict:
    """Get job history with time range filtering"""
    service = JobService(session)
    filters = {}
    if status:
        try:
            filters["state"] = JobState(status.upper())
        except ValueError:
            pass
    if job_type:
        filters["job_type"] = job_type  # type: ignore[assignment]
    try:
        jobs = service.list_jobs(client_id=user["sub"], limit=limit, offset=offset, **filters)
        return {
            "items": service.to_views(jobs),
            "total": len(jobs),
            "limit": limit,
            "offset": offset,
            "from_time": from_time,
            "to_time": to_time,
        }
    except Exception:
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "from_time": from_time,
            "to_time": to_time,
            "error": "Failed to list jobs",
        }


@router.get("/blocks", summary="Get blockchain blocks")
@rate_limit(rate=200, per=60)
async def get_blocks(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Get recent blockchain blocks"""
    try:
        client = AITBCHTTPClient(timeout=5.0)
        try:
            blocks_data = client.get(
                f"{settings.blockchain_rpc_url}/rpc/blocks-range", params={"start": offset, "end": offset + limit}
            )
            return {
                "blocks": blocks_data.get("blocks", []),
                "total": blocks_data.get("total", 0),
                "limit": limit,
                "offset": offset,
            }
        except NetworkError as e:
            logger.error("Failed to fetch blocks: %s", e)
            return {"blocks": [], "total": 0, "limit": limit, "offset": offset, "error": "Failed to fetch blocks"}
    except Exception:
        return {"blocks": [], "total": 0, "limit": limit, "offset": offset, "error": "Failed to fetch blocks"}


@router.post("/jobs/{job_id}/accept", response_model=JobView, summary="Accept a result and release payment")
@rate_limit(rate=50, per=60)
async def accept_job(
    request: Request,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobView:
    """Release the held escrow now, without waiting for the window to expire (G3).

    Accepting is the customer's own decision to pay, so it is the one release path
    that needs no timer and no arbiter.
    """
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=user["sub"])
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    payment = session.get(JobPayment, job.payment_id) if job.payment_id else None
    if not payment or payment.status != PENDING_ACCEPTANCE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job has no payment awaiting acceptance (payment_status={payment.status if payment else job.payment_status})",
        )
    receipt = job.receipt
    payment = session.get(JobPayment, job.payment_id)
    if _zk_required_for_payment(payment.amount if payment else None, job):
        if not receipt or receipt.get("zk_status") != "verified" or receipt.get("computation_correct") is not True:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="job result did not pass the computation-correctness check; acceptance blocked",
            )

    released = await PaymentService(session).release_payment(
        user["sub"], job.id, job.payment_id, reason="Customer accepted the result"
    )
    if not released:
        # The payment stays held, so the sweeper retries it when the window expires
        # rather than leaving the provider unpaid on a transient chain failure.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="the escrow release did not settle on-chain; the payment stays held and will be retried",
        )
    job.payment_status = payment.status
    session.add(job)
    session.commit()
    session.refresh(job)
    logger.info("Client %s accepted job %s; released payment %s", user["sub"], job.id, job.payment_id)
    return service.to_view(job)  # type: ignore[no-any-return]


@router.post("/jobs/{job_id}/reject", response_model=JobView, summary="Reject a result and open a dispute")
@rate_limit(rate=50, per=60)
async def reject_job(
    request: Request,
    job_id: str,
    req: JobRejection,
    session: Annotated[Session, Depends(get_session)],
    user: ClientDep,
) -> JobView:
    """Refuse the delivered result. The escrow stays locked pending a ruling (G3).

    Rejecting does not refund on its own. A customer who could take the money back
    unilaterally would be the mirror of the provider releasing it unilaterally, which
    is the imbalance the acceptance window exists to remove -- so the payment moves to
    "disputed" and an operator or arbiter settles it either way.

    For the same reason it does not slash the provider's bond. A rejection is a claim,
    not a finding: the customer has asserted the result is bad, and nobody has yet
    checked. Burning half a bond on that assertion would hand the buyer a punishment
    the seller has no symmetric answer to, which is the exact power this endpoint was
    written to withhold. The fraud slash belongs to the refund branch of
    POST /v1/admin/disputes/{job_id}/resolve, where an operator has actually ruled.
    """
    service = JobService(session)
    try:
        job = service.get_job(job_id, client_id=user["sub"])
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from None
    payment = session.get(JobPayment, job.payment_id) if job.payment_id else None
    if not payment or payment.status != PENDING_ACCEPTANCE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job has no payment awaiting acceptance (payment_status={payment.status if payment else job.payment_status})",
        )
    if not PaymentService(session).dispute_payment(user["sub"], job.id, job.payment_id, req.reason):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="payment could not be disputed")
    job.payment_status = payment.status
    session.add(job)
    session.commit()
    session.refresh(job)
    logger.info("Client %s rejected job %s: %s", user["sub"], job.id, req.reason)
    return service.to_view(job)  # type: ignore[no-any-return]
