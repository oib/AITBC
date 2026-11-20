"""GPU market registry/bookings routes split from ``market_gpu`` (pure-move).

Import ``coordinator_api.contexts.market.routers.market_gpu`` first (the facade
wires this module's router in); this module is not meant to be imported
directly.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, col, func, select, update

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit
from aitbc_shared import JobPayment

from ....auth import AuthDep, MinerDep
from ....storage.db import get_session
from ...trading.services.trading_market.dynamic_pricing import (
    DynamicPricingEngine,
    PricingStrategy,
    ResourceType,
)
from ..domain.gpu_market import GPUBooking, GPURegistry, GPUReview
from ..services.ollama_queue import get_queue
from ....utils.sql_like import like_contains

from .market_gpu import (
    _OPS_ERRORS,
    _cas_book_gpu,
    _expire_stale_booking,
    _RELEASE_SAFE_PAYMENT_STATUSES,
    GPUBookRequest,
    GPUConfirmRequest,
    GPUSellRequest,
    GPUReviewRequest,
    OllamaTaskRequest,
    get_pricing_engine,
)

logger = get_logger(__name__)

router = APIRouter()

# GPURegistry.price_per_hour is Numeric(20,8): at most 12 integer digits.
# sell_gpu/register_gpu take caller-controlled prices — bound them before
# the write, mirroring the gpu_service #1389 pattern (#1566).
_MAX_PRICE_PER_HOUR = Decimal("999999999999.99999999")


def _validated_price_per_hour(raw: Any) -> Decimal:
    """Return a finite Decimal price in [0, _MAX_PRICE_PER_HOUR] or raise 400."""
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"invalid price_per_hour: {raw!r}") from exc
    if not price.is_finite() or price < 0 or price > _MAX_PRICE_PER_HOUR:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"price_per_hour out of range: {raw!r} (expected 0 <= price <= {_MAX_PRICE_PER_HOUR})",
        )
    return price


def _gpu_to_dict(gpu: GPURegistry) -> dict[str, Any]:
    return {
        "id": gpu.id,
        "miner_id": gpu.miner_id,
        "model": gpu.model,
        "memory_gb": gpu.memory_gb,
        "cuda_version": gpu.cuda_version,
        "region": gpu.region,
        "price_per_hour": gpu.price_per_hour,
        "status": gpu.status,
        "capabilities": gpu.capabilities,
        "created_at": gpu.created_at.isoformat() + "Z",
        "average_rating": gpu.average_rating,
        "total_reviews": gpu.total_reviews,
    }


def _get_gpu_or_404(session: Session, gpu_id: str) -> GPURegistry:
    gpu = session.get(GPURegistry, gpu_id)
    if not gpu:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"GPU {gpu_id} not found")
    return gpu


# Repricing/relisting only while the GPU is not actively booked (#1810 / #1424).
_GPU_RELIST_FROM_STATUSES = frozenset({"available", "offline"})


def _cas_relist_gpu(session: Session, gpu_id: str, listing_price: Decimal) -> bool:
    """Conditional status+price write — the status predicate is the CAS."""
    result = session.execute(
        update(GPURegistry)
        .where(
            col(GPURegistry.id) == gpu_id,
            col(GPURegistry.status).in_(_GPU_RELIST_FROM_STATUSES),
        )
        .values(status="available", price_per_hour=listing_price)
        .execution_options(synchronize_session=False)
    )
    return getattr(result, "rowcount", 0) == 1


@router.post("/market/gpu/register")
@rate_limit(rate=30, per=60)
def register_gpu(
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Register a GPU in the market."""
    gpu_specs = request.get("gpu", {})
    import uuid
    from datetime import datetime

    gpu_id = f"gpu_{uuid.uuid4().hex[:8]}"
    # E1: the authenticated miner is the canonical owner — a caller-supplied
    # miner_id can never register a GPU under someone else's id (#1074).
    miner_id = user.get("sub") or gpu_specs.get("miner_id") or gpu_specs.get("miner") or "default_miner"
    compute_capability = gpu_specs.get("compute_capability", "")
    cuda_version = compute_capability if compute_capability else ""
    price_per_hour = _validated_price_per_hour(gpu_specs.get("price_per_hour", "0.05"))
    # #2291: idempotent per (miner, model, resource_id) so a miner that
    # re-registers on every start does not mint duplicate rows. Only the
    # authenticated miner's own row can match (miner_id comes from the token).
    model_name = gpu_specs.get("name", "Unknown GPU")
    resource_id = gpu_specs.get("resource_id")
    existing = (
        session.execute(
            select(GPURegistry).where(
                col(GPURegistry.miner_id) == miner_id,
                col(GPURegistry.model) == model_name,
                col(GPURegistry.resource_id).is_(None) if resource_id is None else col(GPURegistry.resource_id) == resource_id,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.price_per_hour = price_per_hour
        existing.region = gpu_specs.get("region", existing.region)
        existing.memory_gb = gpu_specs.get("memory_gb", existing.memory_gb)
        if compute_capability:
            existing.cuda_version = cuda_version
        # The model id keys the energy-profile match at purchase; a re-register
        # must be able to correct it (a row registered without one is refused
        # with "quote model_id does not match job model_id").
        if gpu_specs.get("model_id"):
            existing.model_id = gpu_specs["model_id"]
        if "protected" in gpu_specs:
            existing.protected = bool(gpu_specs["protected"])
        session.add(existing)
        session.commit()
        return {
            "gpu_id": existing.id,
            "status": "registered",
            "already_registered": True,
            "message": f"GPU {model_name} already registered",
            "price_per_hour": price_per_hour,
        }
    gpu_record = GPURegistry(
        id=gpu_id,
        miner_id=miner_id,
        model=gpu_specs.get("name", "Unknown GPU"),
        model_id=gpu_specs.get("model_id"),
        memory_gb=gpu_specs.get("memory_gb", 0),
        cuda_version=cuda_version,
        region=gpu_specs.get("region", "localhost"),
        price_per_hour=price_per_hour,
        status="available",
        capabilities=[],
        average_rating=0.0,
        total_reviews=0,
        created_at=datetime.now(UTC),
        resource_id=gpu_specs.get("resource_id"),
        protected=bool(gpu_specs.get("protected")),
    )
    session.add(gpu_record)
    session.commit()
    session.refresh(gpu_record)
    return {
        "gpu_id": gpu_id,
        "status": "registered",
        "already_registered": False,
        "message": f"GPU {gpu_specs.get('name', 'Unknown GPU')} registered successfully",
        "price_per_hour": price_per_hour,
    }


@router.get("/market/gpu/list")
def list_gpus(
    session: Annotated[Session, Depends(get_session)],
    available: bool | None = Query(default=None),
    price_max: Decimal | None = None,
    region: str | None = Query(default=None),
    model: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List GPUs with optional filters."""
    stmt = select(GPURegistry)
    if available is not None:
        target_status = "available" if available else "booked"
        stmt = stmt.where(GPURegistry.status == target_status)
    if price_max is not None:
        stmt = stmt.where(GPURegistry.price_per_hour <= price_max)
    if region:
        stmt = stmt.where(func.lower(GPURegistry.region) == region.lower())
    if model:
        stmt = stmt.where(col(GPURegistry.model).like(like_contains(model), escape="\\"))
    stmt = stmt.limit(limit)
    gpus = session.execute(stmt).scalars().all()
    return [_gpu_to_dict(g) for g in gpus]


@router.get("/market/gpu/{gpu_id}")
def get_gpu_details(gpu_id: str, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get GPU details."""
    gpu = _get_gpu_or_404(session, gpu_id)
    result = _gpu_to_dict(gpu)
    if gpu.status == "booked":
        booking = (
            session.execute(select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1))
            .scalars()
            .first()
        )
        if booking:
            result["current_booking"] = {
                "booking_id": booking.id,
                "duration_hours": booking.duration_hours,
                "total_cost": booking.total_cost,
                "start_time": booking.start_time.isoformat() + "Z",
                "end_time": booking.end_time.isoformat() + "Z" if booking.end_time else None,
            }
    return result


@router.post("/market/gpu/sell")
@rate_limit(rate=20, per=60)
def sell_gpu(
    request: GPUSellRequest, session: Annotated[Session, Depends(get_session)], user: AuthDep, *, http_request: Request
) -> dict[str, Any]:
    """List GPU for sale on market with specified price."""
    gpu = _get_gpu_or_404(session, request.gpu_id)
    if gpu.miner_id != user.get("sub"):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="only the GPU owner may reprice it")
    # #1566: listing_price was stored verbatim — 0/negative/NaN/huge values
    # listable and could win matching or break Numeric(20,8) on overflow.
    listing_price = _validated_price_per_hour(request.listing_price)
    if not _cas_relist_gpu(session, request.gpu_id, listing_price):
        refreshed = _get_gpu_or_404(session, request.gpu_id)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {request.gpu_id} is not available for relisting (status={refreshed.status})",
        )
    session.commit()
    session.refresh(gpu)
    return {
        "gpu_id": request.gpu_id,
        "seller_id": request.seller_id,
        "listing_price": listing_price,
        "status": "listed",
        "description": request.description,
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }


@router.post("/market/gpu/{gpu_id}/book", status_code=http_status.HTTP_201_CREATED)
@rate_limit(rate=30, per=60)
async def book_gpu(
    gpu_id: str,
    request: GPUBookRequest,
    session: Annotated[Session, Depends(get_session)],
    engine: Annotated[DynamicPricingEngine, Depends(get_pricing_engine)],
    user: AuthDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Book a GPU with dynamic pricing."""
    # CE-004: expire a stale unpaid hold before taking the row lock — the
    # reaper commits, which would otherwise drop the FOR UPDATE lock early.
    gpu_preview = session.get(GPURegistry, gpu_id)
    if gpu_preview is not None:
        await run_in_threadpool(_expire_stale_booking, session, gpu_preview)
    # Lock the GPU row while booking: two concurrent bookings could both see
    # "available" and double-book the same GPU (#1802, buy_gpu precedent).
    gpu = await run_in_threadpool(
        lambda: session.exec(select(GPURegistry).where(GPURegistry.id == gpu_id).with_for_update()).first()
    )
    if not gpu:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"GPU {gpu_id} not found")
    if gpu.status != "available":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"GPU {gpu_id} is not available")
    if request.duration_hours <= 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking duration must be greater than 0 hours"
        )
    if request.duration_hours > 8760:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking duration cannot exceed 8760 hours (1 year)"
        )
    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(hours=request.duration_hours)
    if end_time <= start_time:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking end time must be in the future")
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=gpu_id,
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
    duration_dec = Decimal(str(request.duration_hours))
    total_cost = duration_dec * current_price
    booking = GPUBooking(
        gpu_id=gpu_id,
        client_id=user["sub"],
        job_id=request.job_id,
        duration_hours=request.duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        status="active",
    )
    # #1836: CAS the status flip before inserting the hold — FOR UPDATE is a
    # no-op on sqlite, so the predicate in WHERE is the real arbiter. A lost
    # race must not leave a second active booking on the GPU.
    if not await run_in_threadpool(_cas_book_gpu, session, gpu_id):
        await run_in_threadpool(session.rollback)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is not available",
        )
    gpu.status = "booked"
    await run_in_threadpool(session.add, booking)
    await run_in_threadpool(session.add, gpu)
    await run_in_threadpool(session.commit)
    await run_in_threadpool(session.refresh, booking)
    return {
        "booking_id": booking.id,
        "gpu_id": gpu_id,
        "status": "booked",
        "total_cost": booking.total_cost,
        "base_price": gpu.price_per_hour,
        "dynamic_price": current_price,
        "price_per_hour": current_price,
        "start_time": booking.start_time.isoformat() + "Z" if booking.start_time else None,
        "end_time": booking.end_time.isoformat() + "Z" if booking.end_time else None,
        "pricing_factors": dynamic_result.factors_exposed if "dynamic_result" in locals() else {},
        "confidence_score": dynamic_result.confidence_score if "dynamic_result" in locals() else 0.8,
    }


@router.post("/market/gpu/{gpu_id}/release")
@rate_limit(rate=20, per=60)
def release_gpu(
    gpu_id: str, session: Annotated[Session, Depends(get_session)], user: AuthDep, *, request: Request
) -> dict[str, Any]:
    """Release a booked GPU."""
    gpu = _get_gpu_or_404(session, gpu_id)
    _expire_stale_booking(session, gpu)
    if gpu.status != "booked":
        return {"status": "already_available", "gpu_id": gpu_id, "message": f"GPU {gpu_id} is already available"}
    booking = (
        session.execute(select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1))
        .scalars()
        .first()
    )
    caller = user.get("sub")
    is_admin = user.get("role") == "admin"
    if not is_admin and caller != gpu.miner_id and (booking is None or booking.client_id != caller):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="only the GPU owner, the booking client, or an admin may release it",
        )
    # #1913: a paid booking's money lives in Job/JobPayment/escrow — freeing
    # the GPU here would leave the bound job live to settle afterward (the
    # provider still gets paid for a rental the caller believes ended), and
    # a buyer-initiated release would strand the escrow with no refund path.
    # Paid holds end through the job cancel/refund flows; only unpaid holds
    # or bookings whose payment already settled may be released here.
    if booking is not None and booking.payment_id:
        payment = session.get(JobPayment, booking.payment_id)
        if payment is None or payment.status not in _RELEASE_SAFE_PAYMENT_STATUSES:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=("booking has a live payment — cancel or refund the bound job instead of releasing the GPU"),
            )
    refund = Decimal("0")
    if booking:
        try:
            refund = booking.total_cost * Decimal("0.5")
            booking.status = "cancelled"
        except AttributeError as e:
            logger.warning("Booking missing attribute: %s", e)
            refund = Decimal("0")
    gpu.status = "available"
    session.commit()
    return {"status": "released", "gpu_id": gpu_id, "refund": refund, "message": f"GPU {gpu_id} released successfully"}


@router.post("/market/gpu/{gpu_id}/confirm")
@rate_limit(rate=20, per=60)
def confirm_gpu_booking(
    gpu_id: str,
    request: GPUConfirmRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Confirm a booking (client ACK)."""
    gpu = _get_gpu_or_404(session, gpu_id)
    _expire_stale_booking(session, gpu)
    if gpu.status != "booked":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"GPU {gpu_id} is not booked")
    booking = session.execute(
        select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1)
    ).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Active booking for {gpu_id} not found")
    if request.client_id:
        if request.client_id != user.get("sub"):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="client_id must be the authenticated caller",
            )
        booking.client_id = request.client_id
        session.add(booking)
        session.commit()
        session.refresh(booking)
    return {
        "status": "confirmed",
        "gpu_id": gpu_id,
        "booking_id": booking.id,
        "client_id": booking.client_id,
        "message": f"Booking confirmed for GPU {gpu_id}",
    }


@router.post("/tasks/ollama")
@rate_limit(rate=30, per=60)
async def submit_ollama_task(
    request: OllamaTaskRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Submit an Ollama inference task to the persistent Redis queue."""
    await run_in_threadpool(_get_gpu_or_404, session, request.gpu_id)
    queue = await get_queue()
    task_id = await queue.enqueue(
        gpu_id=request.gpu_id,
        model=request.model,
        prompt=request.prompt,
        parameters=request.parameters,
    )
    return {
        "task_id": task_id,
        "gpu_id": request.gpu_id,
        "status": "queued",
        "model": request.model,
    }


@router.delete("/market/gpu/{gpu_id}")
@rate_limit(rate=20, per=60)
def delete_gpu(
    gpu_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    force: bool = Query(default=False, description="Force delete even if GPU is booked"),
    *,
    request: Request,
) -> dict[str, Any]:
    """Delete (unregister) a GPU from the market."""
    gpu = _get_gpu_or_404(session, gpu_id)
    # CE-005: deleting a listing is owner-or-admin only; force-deleting a
    # booked GPU is admin-only.
    caller = user.get("sub")
    is_admin = user.get("role") == "admin"
    if gpu.miner_id != caller and not is_admin:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="only the GPU owner or an admin may delete it",
        )
    if force and not is_admin:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="force delete requires an admin",
        )
    if gpu.status == "booked":
        if not force:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=f"GPU {gpu_id} is currently booked. Use force=true to delete anyway.",
            )
        # #1924: force-delete must not orphan a booking whose payment still has
        # live money — same fail-closed rule as the release guard (#1913).
        booking = (
            session.execute(select(GPUBooking).where(GPUBooking.gpu_id == gpu.id, GPUBooking.status == "active").limit(1))
            .scalars()
            .first()
        )
        if booking is not None and booking.payment_id:
            payment = session.get(JobPayment, booking.payment_id)
            if payment is None or payment.status not in _RELEASE_SAFE_PAYMENT_STATUSES:
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT,
                    detail="GPU has an active booking with a live payment — resolve the payment (cancel or refund the bound job) before force-deleting",
                )
        if booking is not None:
            booking.status = "cancelled"
            session.add(booking)
    session.delete(gpu)
    session.commit()
    return {"status": "deleted", "gpu_id": gpu_id}


@router.get("/market/gpu/{gpu_id}/reviews")
def get_gpu_reviews(
    gpu_id: str, session: Annotated[Session, Depends(get_session)], limit: int = Query(default=10, ge=1, le=100)
) -> dict[str, Any]:
    """Get GPU reviews."""
    gpu = _get_gpu_or_404(session, gpu_id)
    reviews = (
        session.execute(
            select(GPUReview)
            .where(GPUReview.gpu_id == gpu_id)
            .order_by(GPUReview.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return {
        "gpu_id": gpu_id,
        "average_rating": gpu.average_rating,
        "total_reviews": gpu.total_reviews,
        "reviews": [
            {"rating": r.rating, "comment": r.comment, "user": r.user_id, "date": r.created_at.isoformat() + "Z"}
            for r in reviews
        ],
    }


@router.post("/market/gpu/{gpu_id}/reviews", status_code=http_status.HTTP_201_CREATED)
@rate_limit(rate=30, per=60)
def add_gpu_review(
    gpu_id: str,
    request: GPUReviewRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Add a review for a GPU."""
    try:
        gpu = _get_gpu_or_404(session, gpu_id)
        if not 1 <= request.rating <= 5:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Rating must be between 1 and 5")
        reviewer_id = str(user.get("sub") or user.get("user_id") or "unknown")
        review = GPUReview(gpu_id=gpu_id, user_id=reviewer_id, rating=request.rating, comment=request.comment)
        logger.info(
            "Starting review transaction for GPU %s",
            gpu_id,
            extra={"gpu_id": gpu_id, "rating": request.rating, "user_id": reviewer_id},
        )
        session.add(review)
        session.flush()
        total_count_result = session.execute(select(func.count(GPUReview.id)).where(GPUReview.gpu_id == gpu_id)).one()  # type: ignore[arg-type]
        total_count = total_count_result[0] if hasattr(total_count_result, "__getitem__") else total_count_result
        avg_rating_result = session.execute(select(func.avg(GPUReview.rating)).where(GPUReview.gpu_id == gpu_id)).one()
        avg_rating = avg_rating_result[0] if hasattr(avg_rating_result, "__getitem__") else avg_rating_result
        avg_rating = avg_rating or 0.0
        gpu.average_rating = round(float(avg_rating), 2)
        gpu.total_reviews = total_count  # type: ignore[assignment]
        session.commit()
        session.refresh(review)
        logger.info(
            "Review transaction completed successfully for GPU %s",
            gpu_id,
            extra={
                "gpu_id": gpu_id,
                "review_id": review.id,
                "total_reviews": total_count,
                "average_rating": gpu.average_rating,
            },
        )
        return {"status": "review_added", "gpu_id": gpu_id, "review_id": review.id, "average_rating": gpu.average_rating}
    except HTTPException:
        raise
    except _OPS_ERRORS as e:
        logger.error(
            "Failed to add review for GPU %s: %s",
            gpu_id,
            str(e),
            extra={"gpu_id": gpu_id, "exc": str(e), "error_type": type(e).__name__},
        )
        try:
            session.rollback()
        except SQLAlchemyError as rollback_error:
            logger.error("Failed to rollback transaction: %s", str(rollback_error))
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add review"
            ) from rollback_error
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add review") from e
