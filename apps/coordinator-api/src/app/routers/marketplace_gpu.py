"""
GPU marketplace endpoints backed by persistent SQLModel tables.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlmodel import select, func, col

from ..storage import SessionDep
from ..domain.gpu_marketplace import GPURegistry, GPUBooking, GPUReview

router = APIRouter(tags=["marketplace-gpu"])


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
    capabilities: List[str] = []


class GPUBookRequest(BaseModel):
    duration_hours: float
    job_id: Optional[str] = None


class GPUReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gpu_to_dict(gpu: GPURegistry) -> Dict[str, Any]:
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
async def register_gpu(
    request: Dict[str, Any],
    session: SessionDep,
) -> Dict[str, Any]:
    """Register a GPU in the marketplace."""
    gpu_specs = request.get("gpu", {})

    gpu = GPURegistry(
        miner_id=gpu_specs.get("miner_id", ""),
        model=gpu_specs.get("name", "Unknown GPU"),
        memory_gb=gpu_specs.get("memory", 0),
        cuda_version=gpu_specs.get("cuda_version", "Unknown"),
        region=gpu_specs.get("region", "unknown"),
        price_per_hour=gpu_specs.get("price_per_hour", 0.0),
        capabilities=gpu_specs.get("capabilities", []),
    )
    session.add(gpu)
    session.commit()
    session.refresh(gpu)

    return {
        "gpu_id": gpu.id,
        "status": "registered",
        "message": f"GPU {gpu.model} registered successfully",
    }


@router.get("/marketplace/gpu/list")
async def list_gpus(
    session: SessionDep,
    available: Optional[bool] = Query(default=None),
    price_max: Optional[float] = Query(default=None),
    region: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[Dict[str, Any]]:
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
    gpus = session.exec(stmt).all()
    return [_gpu_to_dict(g) for g in gpus]


@router.get("/marketplace/gpu/{gpu_id}")
async def get_gpu_details(gpu_id: str, session: SessionDep) -> Dict[str, Any]:
    """Get GPU details."""
    gpu = _get_gpu_or_404(session, gpu_id)
    result = _gpu_to_dict(gpu)

    if gpu.status == "booked":
        booking = session.exec(
            select(GPUBooking)
            .where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active")
            .limit(1)
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


@router.post("/marketplace/gpu/{gpu_id}/book", status_code=http_status.HTTP_201_CREATED)
async def book_gpu(gpu_id: str, request: GPUBookRequest, session: SessionDep) -> Dict[str, Any]:
    """Book a GPU."""
    gpu = _get_gpu_or_404(session, gpu_id)

    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is not available",
        )

    start_time = datetime.utcnow()
    end_time = start_time + timedelta(hours=request.duration_hours)
    total_cost = request.duration_hours * gpu.price_per_hour

    booking = GPUBooking(
        gpu_id=gpu_id,
        job_id=request.job_id,
        duration_hours=request.duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
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
        "start_time": booking.start_time.isoformat() + "Z",
        "end_time": booking.end_time.isoformat() + "Z",
    }


@router.post("/marketplace/gpu/{gpu_id}/release")
async def release_gpu(gpu_id: str, session: SessionDep) -> Dict[str, Any]:
    """Release a booked GPU."""
    gpu = _get_gpu_or_404(session, gpu_id)

    if gpu.status != "booked":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"GPU {gpu_id} is not booked",
        )

    booking = session.exec(
        select(GPUBooking)
        .where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active")
        .limit(1)
    ).first()

    refund = 0.0
    if booking:
        refund = booking.total_cost * 0.5
        booking.status = "cancelled"

    gpu.status = "available"
    session.commit()

    return {
        "status": "released",
        "gpu_id": gpu_id,
        "refund": refund,
        "message": f"GPU {gpu_id} released successfully",
    }


@router.get("/marketplace/gpu/{gpu_id}/reviews")
async def get_gpu_reviews(
    gpu_id: str,
    session: SessionDep,
    limit: int = Query(default=10, ge=1, le=100),
) -> Dict[str, Any]:
    """Get GPU reviews."""
    gpu = _get_gpu_or_404(session, gpu_id)

    reviews = session.exec(
        select(GPUReview)
        .where(GPUReview.gpu_id == gpu_id)
        .order_by(GPUReview.created_at.desc())
        .limit(limit)
    ).all()

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
    gpu_id: str, request: GPUReviewRequest, session: SessionDep
) -> Dict[str, Any]:
    """Add a review for a GPU."""
    gpu = _get_gpu_or_404(session, gpu_id)

    review = GPUReview(
        gpu_id=gpu_id,
        user_id="current_user",
        rating=request.rating,
        comment=request.comment,
    )
    session.add(review)
    session.flush()  # ensure the new review is visible to aggregate queries

    # Recalculate average from DB (new review already included after flush)
    total_count = session.exec(
        select(func.count(GPUReview.id)).where(GPUReview.gpu_id == gpu_id)
    ).one()
    avg_rating = session.exec(
        select(func.avg(GPUReview.rating)).where(GPUReview.gpu_id == gpu_id)
    ).one() or 0.0

    gpu.average_rating = round(float(avg_rating), 2)
    gpu.total_reviews = total_count
    session.commit()
    session.refresh(review)

    return {
        "status": "review_added",
        "gpu_id": gpu_id,
        "review_id": review.id,
        "average_rating": gpu.average_rating,
    }


@router.get("/marketplace/orders")
async def list_orders(
    session: SessionDep,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """List orders (bookings)."""
    stmt = select(GPUBooking)
    if status:
        stmt = stmt.where(GPUBooking.status == status)
    stmt = stmt.order_by(GPUBooking.created_at.desc()).limit(limit)

    bookings = session.exec(stmt).all()
    orders = []
    for b in bookings:
        gpu = session.get(GPURegistry, b.gpu_id)
        orders.append({
            "order_id": b.id,
            "gpu_id": b.gpu_id,
            "gpu_model": gpu.model if gpu else "unknown",
            "miner_id": gpu.miner_id if gpu else "",
            "duration_hours": b.duration_hours,
            "total_cost": b.total_cost,
            "status": b.status,
            "created_at": b.start_time.isoformat() + "Z",
            "job_id": b.job_id,
        })
    return orders


@router.get("/marketplace/pricing/{model}")
async def get_pricing(model: str, session: SessionDep) -> Dict[str, Any]:
    """Get pricing information for a model."""
    # SQLite JSON doesn't support array contains, so fetch all and filter in Python
    all_gpus = session.exec(select(GPURegistry)).all()
    compatible = [
        g for g in all_gpus
        if any(model.lower() in cap.lower() for cap in (g.capabilities or []))
    ]

    if not compatible:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No GPUs found for model {model}",
        )

    prices = [g.price_per_hour for g in compatible]
    cheapest = min(compatible, key=lambda g: g.price_per_hour)

    return {
        "model": model,
        "min_price": min(prices),
        "max_price": max(prices),
        "average_price": sum(prices) / len(prices),
        "available_gpus": len([g for g in compatible if g.status == "available"]),
        "total_gpus": len(compatible),
        "recommended_gpu": cheapest.id,
    }
