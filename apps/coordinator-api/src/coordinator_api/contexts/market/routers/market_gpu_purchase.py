"""GPU market purchase flow split from ``market_gpu`` (pure-move).

Import ``coordinator_api.contexts.market.routers.market_gpu`` first (the facade
wires this module's router in); this module is not meant to be imported
directly.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc.market.energy_pricing import EnergyPricingError, EnergyQuote
from aitbc.rate_limiting import rate_limit
from aitbc.utils.units import units_to_ait

from ....auth import AuthDep
from ....storage.db import get_session
from ...trading.services.trading_market.dynamic_pricing import (
    DynamicPricingEngine,
    PricingStrategy,
    ResourceType,
)
from ...infrastructure.domain.job import Job
from ..domain.gpu_market import GPUBooking, GPURegistry
from ....utils.client_resolver import resolve_client

from .market_gpu import (
    _OPS_ERRORS,
    _cas_book_gpu,
    _expire_stale_booking,
    GPUBuyRequest,
    get_pricing_engine,
)

logger = get_logger(__name__)

router = APIRouter()


async def _lock_gpu_for_purchase(session: Session, gpu_id: str) -> GPURegistry:
    """Expire a stale unpaid hold, take the row lock and fetch the GPU."""
    # CE-004: expire a stale unpaid hold before taking the row lock — the
    # reaper commits, which would otherwise drop the FOR UPDATE lock early.
    gpu_preview = session.get(GPURegistry, gpu_id)
    if gpu_preview is not None:
        await run_in_threadpool(_expire_stale_booking, session, gpu_preview)
    # Lock the GPU row while booking: two concurrent purchases could both see
    # "available" and double-book the same GPU.
    gpu = await run_in_threadpool(
        lambda: session.exec(select(GPURegistry).where(GPURegistry.id == gpu_id).with_for_update()).first()
    )
    if not gpu:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"GPU {gpu_id} not found")
    if gpu.status != "available":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"GPU {gpu_id} is not available for purchase")
    return gpu


async def _resolve_purchase_terms(
    request: GPUBuyRequest, gpu: GPURegistry, engine: DynamicPricingEngine
) -> tuple[datetime, float, datetime, Decimal, Decimal, EnergyQuote | None]:
    """Resolve start/end times, the dynamic price and the total cost."""
    start_time = datetime.now(UTC)
    duration_hours = request.duration_hours
    # E1: if the buyer supplied a signed energy quote, use its frozen terms.
    supplied_quote: EnergyQuote | None = None
    if request.energy_quote:
        try:
            supplied_quote = EnergyQuote.from_dict(request.energy_quote)
            duration_hours = supplied_quote.duration_seconds / 3600
        except (EnergyPricingError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid energy_quote: {exc}",
            ) from exc
    end_time = start_time + timedelta(hours=duration_hours)
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=gpu.id,
            resource_type=ResourceType.GPU,
            base_price=gpu.price_per_hour,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu.region,
        )
        current_price = dynamic_result.recommended_price
    except _OPS_ERRORS as exc:
        # #1374: pricing-engine failure silently repriced the booking at the
        # static rate — log it so the fallback is visible in ops.
        logger.warning("Dynamic pricing failed for gpu %s, using static price: %s", gpu.id, exc)
        current_price = gpu.price_per_hour
    duration_dec = Decimal(str(duration_hours))
    total_cost = duration_dec * current_price
    if supplied_quote is not None:
        total_cost = units_to_ait(supplied_quote.principal_units)
    return start_time, duration_hours, end_time, current_price, total_cost, supplied_quote


async def _create_purchase_booking(
    session: Session,
    request: GPUBuyRequest,
    gpu: GPURegistry,
    *,
    start_time: datetime,
    end_time: datetime,
    duration_hours: float,
    total_cost: Decimal,
    supplied_quote: EnergyQuote | None,
) -> GPUBooking:
    """Resolve the buyer, build the GPUBooking hold and CAS the GPU to booked."""
    try:
        resolved_client_id, client_ref = await run_in_threadpool(resolve_client, session, request.buyer_id, auto_create=True)
    except ValueError as exc:
        # Unresolvable buyer identity is a caller error, not a server fault —
        # same contract as JobService.resolve_client (#1340/#1378).
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    booking_id = str(uuid4())
    # E1: a supplied quote freezes the resource/model/count/duration.
    quote_resource_id = gpu.resource_id
    quote_model_id = gpu.model_id or gpu.model
    quote_gpu_count = 1
    quote_duration_seconds = max(1, int(duration_hours * 3600))
    if supplied_quote is not None:
        quote_resource_id = supplied_quote.resource_id
        quote_model_id = supplied_quote.model_id
        quote_gpu_count = supplied_quote.gpu_count
        quote_duration_seconds = supplied_quote.duration_seconds
    booking = GPUBooking(
        id=booking_id,
        gpu_id=request.gpu_id,
        client_id=resolved_client_id,
        client_ref=client_ref,
        job_id=f"purchase_{client_ref[:8]}",
        duration_hours=duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        status="active",
        protected=(supplied_quote is not None) or request.protected or gpu.protected,
        resource_id=quote_resource_id,
        model_id=quote_model_id,
        gpu_count=quote_gpu_count,
        duration_seconds=quote_duration_seconds,
        energy_quote_snapshot=request.energy_quote,
    )
    # #1836: CAS the status flip before inserting the hold — FOR UPDATE is a
    # no-op on sqlite, so the predicate in WHERE is the real arbiter. A lost
    # race must not leave a second active booking on the GPU.
    if not await run_in_threadpool(_cas_book_gpu, session, request.gpu_id):
        await run_in_threadpool(session.rollback)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {request.gpu_id} is not available for purchase",
        )
    gpu.status = "booked"
    await run_in_threadpool(session.add, booking)
    await run_in_threadpool(session.add, gpu)
    await run_in_threadpool(session.commit)
    await run_in_threadpool(session.refresh, gpu)
    await run_in_threadpool(session.refresh, booking)
    return booking


async def _open_purchase_job(
    session: Session,
    request: GPUBuyRequest,
    booking: GPUBooking,
    gpu: GPURegistry,
    *,
    start_time: datetime,
    total_cost: Decimal,
    duration_hours: float,
    end_time: datetime,
) -> tuple[Any, str, Decimal, float, datetime]:
    """Create the AI job for the purchase, or bind the prepared job (E1).

    Returns ``(job, job_id, total_cost, duration_hours, end_time)`` — the last
    three may have been rebound to the prepared job's frozen quote terms."""
    from sqlmodel import Session as SQLModelSession

    from ....custom_types import Constraints
    from ....schemas import JobCreate
    from ...infrastructure.services.jobs import JobService

    job_session = SQLModelSession(bind=session.bind)
    job_service = JobService(job_session)
    if request.job_id:
        # E1: a prepared quote already created and bound the job.
        job = await run_in_threadpool(job_session.get, Job, request.job_id)
        if not job:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Prepared job {request.job_id} not found",
            )
        # E1: carry the frozen quote and binding fields from the prepared job.
        quote_snapshot = request.energy_quote or job.energy_quote_snapshot
        if quote_snapshot and job.energy_quote_snapshot:
            supplied = quote_snapshot.get("quote_id")
            stored = job.energy_quote_snapshot.get("quote_id")
            if supplied != stored:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Energy quote does not match the prepared job",
                )
        if quote_snapshot:
            try:
                quote = EnergyQuote.from_dict(quote_snapshot)
                booking.protected = True
                booking.total_cost = units_to_ait(quote.principal_units)
                booking.energy_quote_snapshot = quote.to_dict(include_signature=False)
                booking.duration_seconds = quote.duration_seconds
                booking.duration_hours = quote.duration_seconds / 3600
                booking.gpu_count = quote.gpu_count
                booking.resource_id = quote.resource_id
                booking.model_id = quote.model_id
            except (EnergyPricingError, TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid energy quote for prepared job: {exc}",
                ) from exc
        else:
            booking.protected = job.protected
        booking.job_id = job.id
        job_id = job.id
        total_cost = booking.total_cost
        duration_hours = booking.duration_hours
        end_time = start_time + timedelta(seconds=booking.duration_seconds or 0)
    else:
        duration_dec = Decimal(str(duration_hours))
        job_create = JobCreate(
            payload={
                "type": "gpu_compute",
                "gpu_id": request.gpu_id,
                "task": "general_compute",
                "duration_hours": duration_hours,
                "gpu_count": booking.gpu_count,
            },
            constraints=Constraints(
                gpu=booking.model_id,
                region=gpu.region,
                min_vram_gb=None,
                max_price=total_cost * Decimal("1.1"),
            ),
            ttl_seconds=max(300, int(duration_dec * 3600)),
            payment_amount=total_cost,
            payment_currency="AITBC",
        )
        job = await run_in_threadpool(job_service.create_job, client_id=request.buyer_id, req=job_create)
        job_id = job.id
    job_session.close()  # noqa: unawaited-async — SQLModelSession.close() is synchronous
    logger.info("Using job %s for GPU purchase %s", job_id, booking.id)
    return job, job_id, total_cost, duration_hours, end_time


async def _create_purchase_payment(
    session: Session,
    request: GPUBuyRequest,
    booking: GPUBooking,
    job: Any,
    *,
    total_cost: Decimal,
    duration_hours: float,
) -> tuple[Any, str | None, str | None]:
    """Create the JobPayment for the purchase.

    Payment-rail failures are logged and reported as ``failed`` rather than
    raised — the caller rolls the booking back on failed/skipped. Returns
    ``(payment, payment_id, payment_status)``."""
    from sqlmodel import Session as SQLModelSession

    from ....contexts.payments.services.payments import PaymentService
    from ....schemas import JobPaymentCreate

    payment: Any = None
    payment_id: str | None = None
    payment_status: str | None = None
    try:
        payment_session = SQLModelSession(bind=session.bind)
        payment_service = PaymentService(payment_session)
        quote_payload = request.energy_quote or (job.energy_quote_snapshot if request.job_id else None)

        # Resolve the payment method. The CLI sends "blockchain" for the
        # legacy native path or "evm" for EVM-protected rentals. The
        # PaymentService expects "aitbc_token" for the native rail and
        # "evm" for the EVM rail.
        if request.payment_method == "blockchain":
            payment_method = "aitbc_token"
        else:
            payment_method = request.payment_method

        from ...payments.services.escrow_agent_binding import (
            assert_agent_address_binding,
            default_resolve_chain_id,
            resolve_agent_payment_address,
        )

        resolve_chain = default_resolve_chain_id()
        buyer_address = request.buyer_address
        provider_address = request.provider_address
        if request.buyer_agent_id:
            if buyer_address:
                await assert_agent_address_binding(
                    session, request.buyer_agent_id, buyer_address, role="buyer", chain_id=resolve_chain
                )
            else:
                buyer_address = await resolve_agent_payment_address(session, request.buyer_agent_id, resolve_chain)
        if request.provider_agent_id:
            if provider_address:
                await assert_agent_address_binding(
                    session, request.provider_agent_id, provider_address, role="provider", chain_id=resolve_chain
                )
            else:
                provider_address = await resolve_agent_payment_address(session, request.provider_agent_id, resolve_chain)
        payment_create = JobPaymentCreate(
            job_id=job.id,
            amount=total_cost,
            currency="AITBC",
            payment_method=payment_method,
            escrow_timeout_seconds=max(300, int(duration_hours * 3600)),
            protected=booking.protected,
            energy_quote=quote_payload,
            buyer_address=buyer_address,
            provider_address=provider_address,
            buyer_lock_signature=request.buyer_lock_signature,
            buyer_lock_nonce=request.buyer_lock_nonce,
            buyer_lock_fee=request.buyer_lock_fee,
            evm_tx_hash=request.evm_tx_hash,
            evm_agreement_id=request.evm_agreement_id,
            evm_escrow_id=request.evm_escrow_id,
            buyer_agent_id=request.buyer_agent_id,
            provider_agent_id=request.provider_agent_id,
        )
        payment = await payment_service.create_payment(client_id=request.buyer_id, job_id=job.id, payment_data=payment_create)
        payment_id = payment.id
        payment_status = payment.status
        payment_session.close()  # noqa: unawaited-async — SQLModelSession.close() is synchronous
        logger.info("Created payment %s for job %s", payment.id, job.id)
    except _OPS_ERRORS as e:
        logger.error("Failed to create payment for job %s: %s", job.id, e)
        payment_id = None
        payment_status = "failed"
    return payment, payment_id, payment_status


async def _buy_gpu_job_payment(
    session: Session,
    request: GPUBuyRequest,
    booking: GPUBooking,
    gpu: GPURegistry,
    *,
    start_time: datetime,
    total_cost: Decimal,
    duration_hours: float,
    end_time: datetime,
) -> tuple[Any, str | None, str | None, Any, Decimal, float, datetime]:
    """Create the purchase's job + payment and persist the booking linkage.

    On validation failure the booking/GPU committed above are released before
    the exception propagates; on payment failure the booking is rolled back
    and a 402 is raised. Returns
    ``(job_id, payment_id, payment_status, payment, total_cost, duration_hours, end_time)``."""
    job_id: str | None = None
    payment_id: str | None = None
    payment_status: str | None = None
    payment: Any = None
    try:
        job, job_id, total_cost, duration_hours, end_time = await _open_purchase_job(
            session,
            request,
            booking,
            gpu,
            start_time=start_time,
            total_cost=total_cost,
            duration_hours=duration_hours,
            end_time=end_time,
        )
        payment, payment_id, payment_status = await _create_purchase_payment(
            session, request, booking, job, total_cost=total_cost, duration_hours=duration_hours
        )
        booking.job_id = job.id
        booking.payment_id = payment_id
        await run_in_threadpool(session.add, booking)
        await run_in_threadpool(session.commit)
        logger.info("Successfully created job %s and payment %s for GPU purchase %s", job.id, payment_id, booking.id)
    except HTTPException:
        # Validation failures (prepared-job 404/422, binding 403) must still
        # release the booking/GPU committed above before propagating.
        if job_id is not None:
            existing_job = await run_in_threadpool(session.get, Job, job_id)
            if existing_job and existing_job.state in ("QUEUED", "RUNNING"):
                existing_job.state = "CANCELED"
                existing_job.error = "Payment failed"
                await run_in_threadpool(session.add, existing_job)
        await run_in_threadpool(session.delete, booking)
        gpu.status = "available"
        await run_in_threadpool(session.commit)
        raise
    except _OPS_ERRORS as e:
        logger.error("Failed to create job/payment for GPU purchase: %s", e)

    # Payment failure rolls back booking and GPU; the job is cancelled if payment
    # never succeeded, so we don't return a fake "purchased" status.
    if payment_status in ("failed", "skipped") or job_id is None:
        if job_id is not None:
            existing_job = await run_in_threadpool(session.get, Job, job_id)
            if existing_job and existing_job.state in ("QUEUED", "RUNNING"):
                existing_job.state = "CANCELED"
                existing_job.error = "Payment failed"
                await run_in_threadpool(session.add, existing_job)
        await run_in_threadpool(session.delete, booking)
        gpu.status = "available"
        await run_in_threadpool(session.commit)
        detail = f"Payment failed: {payment_status}"
        escrow_error = getattr(payment, "meta_data", None)
        if isinstance(escrow_error, dict) and escrow_error.get("escrow_error"):
            detail = f"Payment failed: {escrow_error['escrow_error']}"
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
        )
    return job_id, payment_id, payment_status, payment, total_cost, duration_hours, end_time


@router.post("/market/gpu/purchase")
@rate_limit(rate=20, per=60)
async def buy_gpu(
    request: GPUBuyRequest,
    session: Annotated[Session, Depends(get_session)],
    engine: Annotated[DynamicPricingEngine, Depends(get_pricing_engine)],
    user: AuthDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Buy GPU compute from market with blockchain payment and AI job scheduling."""
    # #1075: the purchase must belong to the caller — a body-supplied buyer_id
    # let a client book a rental on someone else's account.
    if request.buyer_id != user["sub"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="buyer_id does not match authenticated buyer")
    gpu = await _lock_gpu_for_purchase(session, request.gpu_id)
    start_time, duration_hours, end_time, current_price, total_cost, supplied_quote = await _resolve_purchase_terms(
        request, gpu, engine
    )
    booking = await _create_purchase_booking(
        session,
        request,
        gpu,
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration_hours,
        total_cost=total_cost,
        supplied_quote=supplied_quote,
    )
    job_id, payment_id, payment_status, _payment, total_cost, duration_hours, end_time = await _buy_gpu_job_payment(
        session,
        request,
        booking,
        gpu,
        start_time=start_time,
        total_cost=total_cost,
        duration_hours=duration_hours,
        end_time=end_time,
    )

    return {
        "purchase_id": booking.id,
        "gpu_id": request.gpu_id,
        "buyer_id": request.buyer_id,
        "job_id": job_id,
        "payment_id": payment_id,
        "duration_hours": duration_hours,
        "total_cost": total_cost,
        "price_per_hour": current_price,
        "status": "purchased",
        "payment_method": request.payment_method,
        "payment_status": payment_status,
        "start_time": start_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
    }
