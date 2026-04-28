from typing import Annotated, Optional

"""
GPU marketplace endpoints backed by persistent SQLModel tables.
"""

import statistics
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlmodel import col, func, select

from aitbc import get_logger
from ..custom_types import Constraints
from ..domain.gpu_marketplace import GPUBooking, GPURegistry, GPUReview
from ..domain.job import Job
from ..schemas import JobCreate, JobPaymentCreate
from ..services.dynamic_pricing_engine import DynamicPricingEngine, PricingStrategy, ResourceType
from ..services.jobs import JobService
from ..services.market_data_collector import MarketDataCollector
from ..services.payments import PaymentService
from ..storage.db import get_session

logger = get_logger(__name__)

router = APIRouter(tags=["marketplace-gpu"])

# Global instances (in production, these would be dependency injected)
pricing_engine = None
market_collector = None


async def get_pricing_engine() -> DynamicPricingEngine:
    """Get pricing engine instance"""
    global pricing_engine
    if pricing_engine is None:
        pricing_engine = DynamicPricingEngine(
            {"min_price": 0.001, "max_price": 1000.0, "update_interval": 300, "forecast_horizon": 72}
        )
        await pricing_engine.initialize()
    return pricing_engine


async def get_market_collector() -> MarketDataCollector:
    """Get market data collector instance"""
    global market_collector
    if market_collector is None:
        market_collector = MarketDataCollector({"websocket_port": 8765})
        await market_collector.initialize()
    return market_collector


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class GPURegisterRequest(BaseModel):
    miner_id: str
    model: str
    memory_gb: int
    cuda_version: str
    region: str
    price_per_hour: float
    capabilities: list[str] = []


class GPUBookRequest(BaseModel):
    duration_hours: float
    job_id: str | None = None


class GPUConfirmRequest(BaseModel):
    client_id: str | None = None


class OllamaTaskRequest(BaseModel):
    gpu_id: str
    model: str = "llama2"
    prompt: str
    parameters: dict[str, Any] = {}


class GPUBuyRequest(BaseModel):
    buyer_id: str
    gpu_id: str
    duration_hours: float
    payment_method: str = "blockchain"


class GPUSellRequest(BaseModel):
    seller_id: str
    gpu_id: str
    listing_price: float
    description: Optional[str] = ""


class PaymentRequest(BaseModel):
    from_wallet: str
    to_wallet: str
    amount: float
    booking_id: str | None = None
    task_id: str | None = None


class GPUReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _get_gpu_or_404(session, gpu_id: str) -> GPURegistry:
    gpu = session.get(GPURegistry, gpu_id)
    if not gpu:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"GPU {gpu_id} not found",
        )
    return gpu


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/marketplace/gpu/register")
async def register_gpu(request: dict[str, Any], session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Register a GPU in the marketplace."""
    gpu_specs = request.get("gpu", {})

    # Create GPU registry record
    import uuid
    from datetime import datetime

    gpu_id = f"gpu_{uuid.uuid4().hex[:8]}"
    
    # Ensure miner_id is always provided
    miner_id = gpu_specs.get("miner_id") or gpu_specs.get("miner") or "default_miner"
    
    # Map compute capability to cuda_version field
    compute_capability = gpu_specs.get("compute_capability", "")
    cuda_version = compute_capability if compute_capability else ""
    
    gpu_record = GPURegistry(
        id=gpu_id,
        miner_id=miner_id,
        model=gpu_specs.get("name", "Unknown GPU"),
        memory_gb=gpu_specs.get("memory_gb", 0),
        cuda_version=cuda_version,
        region="default",
        price_per_hour=gpu_specs.get("price_per_hour", 0.05),
        status="available",
        capabilities=[],
        average_rating=0.0,
        total_reviews=0,
        created_at=datetime.utcnow()
    )
    
    session.add(gpu_record)
    session.commit()
    session.refresh(gpu_record)

    return {
        "gpu_id": gpu_id,
        "status": "registered",
        "message": f"GPU {gpu_specs.get('name', 'Unknown GPU')} registered successfully",
        "price_per_hour": gpu_specs.get("price_per_hour", 0.05),
    }


@router.get("/marketplace/gpu/list")
async def list_gpus(
    session: Annotated[Session, Depends(get_session)],
    available: bool | None = Query(default=None),
    price_max: float | None = Query(default=None),
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
        stmt = stmt.where(col(GPURegistry.model).contains(model))

    stmt = stmt.limit(limit)
    gpus = session.execute(stmt).scalars().all()
    return [_gpu_to_dict(g) for g in gpus]


@router.get("/marketplace/gpu/{gpu_id}")
async def get_gpu_details(gpu_id: str, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get GPU details."""
    gpu = _get_gpu_or_404(session, gpu_id)
    result = _gpu_to_dict(gpu)

    if gpu.status == "booked":
        booking = session.execute(
            select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1)
        ).first()
        if booking:
            result["current_booking"] = {
                "booking_id": booking.id,
                "duration_hours": booking.duration_hours,
                "total_cost": booking.total_cost,
                "start_time": booking.start_time.isoformat() + "Z",
                "end_time": booking.end_time.isoformat() + "Z" if booking.end_time else None,
            }
    return result


@router.post("/marketplace/gpu/purchase")
async def buy_gpu(
    request: GPUBuyRequest,
    session: Annotated[Session, Depends(get_session)],
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
) -> dict[str, Any]:
    """Buy GPU compute from marketplace with blockchain payment and AI job scheduling."""
    gpu = _get_gpu_or_404(session, request.gpu_id)

    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {request.gpu_id} is not available for purchase",
        )

    # Create booking for the purchase
    from datetime import datetime, timedelta
    
    start_time = datetime.utcnow()
    end_time = start_time + timedelta(hours=request.duration_hours)
    
    # Calculate total cost
    try:
        dynamic_result = await engine.calculate_price(
            base_price=gpu.price_per_hour,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu.region,
        )
        current_price = dynamic_result.recommended_price
    except Exception:
        current_price = gpu.price_per_hour

    total_cost = request.duration_hours * current_price

    # Create AI job for GPU compute
    job_service = JobService(session)
    job_create = JobCreate(
        payload={
            "type": "gpu_compute",
            "gpu_id": request.gpu_id,
            "task": "general_compute",
            "duration_hours": request.duration_hours,
        },
        constraints=Constraints(
            gpu=gpu.model,
            region=gpu.region,
            min_vram_gb=gpu.memory_gb if gpu.memory_gb else None,
            max_price=current_price * 1.1,  # Allow 10% price variance
        ),
        ttl_seconds=int(request.duration_hours * 3600),
        payment_amount=total_cost,
        payment_currency="AITBC",
    )
    job = job_service.create_job(client_id=request.buyer_id, req=job_create)

    # Create payment for the job
    payment_service = PaymentService(session)
    payment_create = JobPaymentCreate(
        job_id=job.id,
        amount=total_cost,
        currency="AITBC",
        payment_method="aitbc_token" if request.payment_method == "blockchain" else request.payment_method,
        escrow_timeout_seconds=int(request.duration_hours * 3600),
    )
    payment = await payment_service.create_payment(job_id=job.id, payment_data=payment_create)

    # Update job with payment reference
    job.payment_id = payment.id
    job.payment_status = payment.status
    session.add(job)
    session.commit()

    # Create booking linked to the job
    booking_id = str(uuid4())
    booking = GPUBooking(
        id=booking_id,
        gpu_id=request.gpu_id,
        client_id=request.buyer_id,
        job_id=job.id,
        duration_hours=request.duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        status="active",
    )
    
    # Update GPU status
    gpu.status = "booked"
    
    session.add(booking)
    session.commit()
    session.refresh(gpu)
    session.refresh(booking)

    return {
        "purchase_id": booking_id,
        "gpu_id": request.gpu_id,
        "buyer_id": request.buyer_id,
        "job_id": job.id,
        "payment_id": payment.id,
        "duration_hours": request.duration_hours,
        "total_cost": total_cost,
        "price_per_hour": current_price,
        "status": "purchased",
        "payment_method": request.payment_method,
        "payment_status": payment.status,
        "start_time": start_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
    }


@router.post("/marketplace/gpu/sell")
async def sell_gpu(
    request: GPUSellRequest,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """List GPU for sale on marketplace with specified price."""
    gpu = _get_gpu_or_404(session, request.gpu_id)

    # Update GPU listing
    gpu.price_per_hour = request.listing_price
    gpu.status = "available"
    
    session.commit()
    session.refresh(gpu)

    return {
        "gpu_id": request.gpu_id,
        "seller_id": request.seller_id,
        "listing_price": request.listing_price,
        "status": "listed",
        "description": request.description,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/marketplace/gpu/{gpu_id}/book", status_code=http_status.HTTP_201_CREATED)
async def book_gpu(
    gpu_id: str,
    request: GPUBookRequest,
    session: Annotated[Session, Depends(get_session)],
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
) -> dict[str, Any]:
    """Book a GPU with dynamic pricing."""
    gpu = _get_gpu_or_404(session, gpu_id)

    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is not available",
        )

    # Input validation for booking duration
    if request.duration_hours <= 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking duration must be greater than 0 hours"
        )

    if request.duration_hours > 8760:  # 1 year maximum
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking duration cannot exceed 8760 hours (1 year)"
        )

    start_time = datetime.utcnow()
    end_time = start_time + timedelta(hours=request.duration_hours)

    # Validate booking end time is in the future
    if end_time <= start_time:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking end time must be in the future")

    # Calculate dynamic price at booking time
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=gpu_id,
            resource_type=ResourceType.GPU,
            base_price=gpu.price_per_hour,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu.region,
        )
        # Use dynamic price for this booking
        current_price = dynamic_result.recommended_price
    except Exception:
        # Fallback to stored price if dynamic pricing fails
        current_price = gpu.price_per_hour

    total_cost = request.duration_hours * current_price

    booking = GPUBooking(
        gpu_id=gpu_id,
        job_id=request.job_id,
        duration_hours=request.duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        status="active",
    )
    gpu.status = "booked"
    session.add(booking)
    session.commit()
    session.refresh(booking)

    return {
        "booking_id": booking.id,
        "gpu_id": gpu_id,
        "status": "booked",
        "total_cost": booking.total_cost,
        "base_price": gpu.price_per_hour,
        "dynamic_price": current_price,
        "price_per_hour": current_price,
        "start_time": booking.start_time.isoformat() + "Z",
        "end_time": booking.end_time.isoformat() + "Z",
        "pricing_factors": dynamic_result.factors_exposed if "dynamic_result" in locals() else {},
        "confidence_score": dynamic_result.confidence_score if "dynamic_result" in locals() else 0.8,
    }


@router.post("/marketplace/gpu/{gpu_id}/release")
async def release_gpu(gpu_id: str, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Release a booked GPU."""
    gpu = _get_gpu_or_404(session, gpu_id)

    # Allow release even if GPU is not properly booked (cleanup case)
    if gpu.status != "booked":
        # GPU is already available, just return success
        return {
            "status": "already_available",
            "gpu_id": gpu_id,
            "message": f"GPU {gpu_id} is already available",
        }

    booking = session.execute(
        select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1)
    ).first()

    refund = 0.0
    if booking:
        try:
            refund = booking.total_cost * 0.5
            booking.status = "cancelled"
        except AttributeError as e:
            logger.warning(f"Booking missing attribute: {e}")
            refund = 0.0

    gpu.status = "available"
    session.commit()

    return {
        "status": "released",
        "gpu_id": gpu_id,
        "refund": refund,
        "message": f"GPU {gpu_id} released successfully",
    }


# ---------------------------------------------------------------------------
# New endpoints: confirm booking, submit Ollama task, payment hook
# ---------------------------------------------------------------------------


@router.post("/marketplace/gpu/{gpu_id}/confirm")
async def confirm_gpu_booking(
    gpu_id: str,
    request: GPUConfirmRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Confirm a booking (client ACK)."""
    gpu = _get_gpu_or_404(session, gpu_id)

    if gpu.status != "booked":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is not booked",
        )

    booking = session.execute(
        select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1)
    ).scalar_one_or_none()

    if not booking:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Active booking for {gpu_id} not found",
        )

    if request.client_id:
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
async def submit_ollama_task(
    request: OllamaTaskRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Stub Ollama task submission endpoint."""
    # Ensure GPU exists and is booked
    gpu = _get_gpu_or_404(session, request.gpu_id)
    if gpu.status != "booked":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {request.gpu_id} is not booked",
        )

    task_id = f"task_{uuid4().hex[:10]}"
    submitted_at = datetime.utcnow().isoformat() + "Z"

    return {
        "task_id": task_id,
        "status": "submitted",
        "submitted_at": submitted_at,
        "gpu_id": request.gpu_id,
        "model": request.model,
        "prompt": request.prompt,
        "parameters": request.parameters,
    }


@router.post("/payments/send")
async def send_payment(
    request: PaymentRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Stub payment endpoint (hook for blockchain processor)."""
    if request.amount <= 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero",
        )

    tx_id = f"tx_{uuid4().hex[:10]}"
    processed_at = datetime.utcnow().isoformat() + "Z"

    return {
        "tx_id": tx_id,
        "status": "processed",
        "processed_at": processed_at,
        "from": request.from_wallet,
        "to": request.to_wallet,
        "amount": request.amount,
        "booking_id": request.booking_id,
        "task_id": request.task_id,
    }


@router.delete("/marketplace/gpu/{gpu_id}")
async def delete_gpu(
    gpu_id: str,
    session: Annotated[Session, Depends(get_session)],
    force: bool = Query(default=False, description="Force delete even if GPU is booked"),
) -> dict[str, Any]:
    """Delete (unregister) a GPU from the marketplace."""
    gpu = _get_gpu_or_404(session, gpu_id)

    if gpu.status == "booked" and not force:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is currently booked. Use force=true to delete anyway.",
        )

    session.delete(gpu)
    session.commit()
    return {"status": "deleted", "gpu_id": gpu_id}


@router.get("/marketplace/gpu/{gpu_id}/reviews")
async def get_gpu_reviews(
    gpu_id: str,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """Get GPU reviews."""
    gpu = _get_gpu_or_404(session, gpu_id)

    reviews = (
        session.execute(select(GPUReview).where(GPUReview.gpu_id == gpu_id).order_by(GPUReview.created_at.desc()))
        .scalars()
        .all()
    )

    return {
        "gpu_id": gpu_id,
        "average_rating": gpu.average_rating,
        "total_reviews": gpu.total_reviews,
        "reviews": [
            {
                "rating": r.rating,
                "comment": r.comment,
                "user": r.user_id,
                "date": r.created_at.isoformat() + "Z",
            }
            for r in reviews
        ],
    }


@router.post("/marketplace/gpu/{gpu_id}/reviews", status_code=http_status.HTTP_201_CREATED)
async def add_gpu_review(
    gpu_id: str, request: GPUReviewRequest, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Add a review for a GPU."""
    try:
        gpu = _get_gpu_or_404(session, gpu_id)

        # Validate request data
        if not (1 <= request.rating <= 5):
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Rating must be between 1 and 5")

        # Create review object
        review = GPUReview(
            gpu_id=gpu_id,
            user_id="current_user",
            rating=request.rating,
            comment=request.comment,
        )

        # Log transaction start
        logger.info(
            f"Starting review transaction for GPU {gpu_id}",
            extra={"gpu_id": gpu_id, "rating": request.rating, "user_id": "current_user"},
        )

        # Add review to session
        session.add(review)
        session.flush()  # ensure the new review is visible to aggregate queries

        # Recalculate average from DB (new review already included after flush)
        total_count_result = session.execute(select(func.count(GPUReview.id)).where(GPUReview.gpu_id == gpu_id)).one()
        total_count = total_count_result[0] if hasattr(total_count_result, "__getitem__") else total_count_result

        avg_rating_result = session.execute(select(func.avg(GPUReview.rating)).where(GPUReview.gpu_id == gpu_id)).one()
        avg_rating = avg_rating_result[0] if hasattr(avg_rating_result, "__getitem__") else avg_rating_result
        avg_rating = avg_rating or 0.0

        # Update GPU stats
        gpu.average_rating = round(float(avg_rating), 2)
        gpu.total_reviews = total_count

        # Commit transaction
        session.commit()

        # Refresh review object
        session.refresh(review)

        # Log success
        logger.info(
            f"Review transaction completed successfully for GPU {gpu_id}",
            extra={
                "gpu_id": gpu_id,
                "review_id": review.id,
                "total_reviews": total_count,
                "average_rating": gpu.average_rating,
            },
        )

        return {
            "status": "review_added",
            "gpu_id": gpu_id,
            "review_id": review.id,
            "average_rating": gpu.average_rating,
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log error and rollback transaction
        logger.error(
            f"Failed to add review for GPU {gpu_id}: {str(e)}",
            extra={"gpu_id": gpu_id, "error": str(e), "error_type": type(e).__name__},
        )

        # Rollback on error
        try:
            session.rollback()
        except Exception as rollback_error:
            logger.error(f"Failed to rollback transaction: {str(rollback_error)}")

        # Return generic error
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add review")


@router.get("/marketplace/orders")
async def list_orders(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List orders (bookings)."""
    stmt = select(GPUBooking)
    if status:
        stmt = stmt.where(GPUBooking.status == status)
    stmt = stmt.order_by(GPUBooking.created_at.desc()).limit(limit)

    bookings = session.execute(stmt).scalars().all()
    orders = []
    for b in bookings:
        gpu = session.get(GPURegistry, b.gpu_id)
        orders.append(
            {
                "order_id": b.id,
                "gpu_id": b.gpu_id,
                "gpu_model": gpu.model if gpu else "unknown",
                "miner_id": gpu.miner_id if gpu else "",
                "duration_hours": b.duration_hours,
                "total_cost": b.total_cost,
                "status": b.status,
                "created_at": b.start_time.isoformat() + "Z",
                "job_id": b.job_id,
            }
        )
    return orders


@router.get("/marketplace/pricing/{model}")
async def get_pricing(
    model: str,
    session: Annotated[Session, Depends(get_session)],
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
    collector: MarketDataCollector = Depends(get_market_collector),
) -> dict[str, Any]:
    """Get enhanced pricing information for a model with dynamic pricing."""
    # SQLite JSON doesn't support array contains, so fetch all and filter in Python
    all_gpus = session.execute(select(GPURegistry)).scalars().all()
    compatible = [g for g in all_gpus if model.lower() in g.model.lower()]

    if not compatible:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No GPUs found for model {model}",
        )

    # Get static pricing information
    static_prices = [g.price_per_hour for g in compatible]
    cheapest = min(compatible, key=lambda g: g.price_per_hour)

    # Calculate dynamic prices for compatible GPUs
    dynamic_prices = []
    for gpu in compatible:
        try:
            dynamic_result = await engine.calculate_dynamic_price(
                resource_id=gpu.id,
                resource_type=ResourceType.GPU,
                base_price=gpu.price_per_hour,
                strategy=PricingStrategy.MARKET_BALANCE,
                region=gpu.region,
            )
            dynamic_prices.append(
                {
                    "gpu_id": gpu.id,
                    "static_price": gpu.price_per_hour,
                    "dynamic_price": dynamic_result.recommended_price,
                    "price_change": dynamic_result.recommended_price - gpu.price_per_hour,
                    "price_change_percent": ((dynamic_result.recommended_price - gpu.price_per_hour) / gpu.price_per_hour)
                    * 100,
                    "confidence": dynamic_result.confidence_score,
                    "trend": dynamic_result.price_trend.value,
                    "reasoning": dynamic_result.reasoning,
                }
            )
        except Exception:
            # Fallback to static price if dynamic pricing fails
            dynamic_prices.append(
                {
                    "gpu_id": gpu.id,
                    "static_price": gpu.price_per_hour,
                    "dynamic_price": gpu.price_per_hour,
                    "price_change": 0.0,
                    "price_change_percent": 0.0,
                    "confidence": 0.5,
                    "trend": "unknown",
                    "reasoning": ["Dynamic pricing unavailable"],
                }
            )

    # Calculate aggregate dynamic pricing metrics
    dynamic_price_values = [dp["dynamic_price"] for dp in dynamic_prices]
    avg_dynamic_price = sum(dynamic_price_values) / len(dynamic_price_values)

    # Find best value GPU (considering price and confidence)
    best_value_gpu = min(dynamic_prices, key=lambda x: x["dynamic_price"] / x["confidence"])

    # Get market analysis
    market_analysis = None
    try:
        # Get market data for the most common region
        regions = [gpu.region for gpu in compatible]
        most_common_region = max(set(regions), key=regions.count) if regions else "global"

        market_data = await collector.get_aggregated_data("gpu", most_common_region)
        if market_data:
            market_analysis = {
                "demand_level": market_data.demand_level,
                "supply_level": market_data.supply_level,
                "market_volatility": market_data.price_volatility,
                "utilization_rate": market_data.utilization_rate,
                "market_sentiment": market_data.market_sentiment,
                "confidence_score": market_data.confidence_score,
            }
    except Exception:
        market_analysis = None

    return {
        "model": model,
        "static_pricing": {
            "min_price": min(static_prices),
            "max_price": max(static_prices),
            "average_price": sum(static_prices) / len(static_prices),
            "available_gpus": len([g for g in compatible if g.status == "available"]),
            "total_gpus": len(compatible),
            "recommended_gpu": cheapest.id,
        },
        "dynamic_pricing": {
            "min_price": min(dynamic_price_values),
            "max_price": max(dynamic_price_values),
            "average_price": avg_dynamic_price,
            "price_volatility": statistics.stdev(dynamic_price_values) if len(dynamic_price_values) > 1 else 0,
            "avg_confidence": sum(dp["confidence"] for dp in dynamic_prices) / len(dynamic_prices),
            "recommended_gpu": best_value_gpu["gpu_id"],
            "recommended_price": best_value_gpu["dynamic_price"],
        },
        "price_comparison": {
            "avg_price_change": avg_dynamic_price - (sum(static_prices) / len(static_prices)),
            "avg_price_change_percent": (
                (avg_dynamic_price - (sum(static_prices) / len(static_prices))) / (sum(static_prices) / len(static_prices))
            )
            * 100,
            "gpus_with_price_increase": len([dp for dp in dynamic_prices if dp["price_change"] > 0]),
            "gpus_with_price_decrease": len([dp for dp in dynamic_prices if dp["price_change"] < 0]),
        },
        "individual_gpu_pricing": dynamic_prices,
        "market_analysis": market_analysis,
        "pricing_timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/marketplace/gpu/bid")
async def bid_gpu(request: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    """Place a bid on a GPU"""
    # Simple implementation
    bid_id = str(uuid4())
    return {
        "bid_id": bid_id,
        "status": "placed",
        "gpu_id": request.get("gpu_id"),
        "bid_amount": request.get("bid_amount"),
        "duration_hours": request.get("duration_hours"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
