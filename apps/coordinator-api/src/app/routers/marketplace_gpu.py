"""
GPU marketplace endpoints backed by persistent SQLModel tables.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import statistics

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlmodel import select, func, col

from ..storage import SessionDep
from ..domain.gpu_marketplace import GPURegistry, GPUBooking, GPUReview
from ..services.dynamic_pricing_engine import DynamicPricingEngine, PricingStrategy, ResourceType
from ..services.market_data_collector import MarketDataCollector

router = APIRouter(tags=["marketplace-gpu"])

# Global instances (in production, these would be dependency injected)
pricing_engine = None
market_collector = None


async def get_pricing_engine() -> DynamicPricingEngine:
    """Get pricing engine instance"""
    global pricing_engine
    if pricing_engine is None:
        pricing_engine = DynamicPricingEngine({
            "min_price": 0.001,
            "max_price": 1000.0,
            "update_interval": 300,
            "forecast_horizon": 72
        })
        await pricing_engine.initialize()
    return pricing_engine


async def get_market_collector() -> MarketDataCollector:
    """Get market data collector instance"""
    global market_collector
    if market_collector is None:
        market_collector = MarketDataCollector({
            "websocket_port": 8765
        })
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
    engine: DynamicPricingEngine = Depends(get_pricing_engine)
) -> Dict[str, Any]:
    """Register a GPU in the marketplace with dynamic pricing."""
    gpu_specs = request.get("gpu", {})

    # Get initial price from request or calculate dynamically
    base_price = gpu_specs.get("price_per_hour", 0.05)
    
    # Calculate dynamic price for new GPU
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=f"new_gpu_{gpu_specs.get('miner_id', 'unknown')}",
            resource_type=ResourceType.GPU,
            base_price=base_price,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu_specs.get("region", "global")
        )
        # Use dynamic price for initial listing
        initial_price = dynamic_result.recommended_price
    except Exception:
        # Fallback to base price if dynamic pricing fails
        initial_price = base_price

    gpu = GPURegistry(
        miner_id=gpu_specs.get("miner_id", ""),
        model=gpu_specs.get("name", "Unknown GPU"),
        memory_gb=gpu_specs.get("memory", 0),
        cuda_version=gpu_specs.get("cuda_version", "Unknown"),
        region=gpu_specs.get("region", "unknown"),
        price_per_hour=initial_price,
        capabilities=gpu_specs.get("capabilities", []),
    )
    session.add(gpu)
    session.commit()
    session.refresh(gpu)

    # Set up pricing strategy for this GPU provider
    await engine.set_provider_strategy(
        provider_id=gpu.miner_id,
        strategy=PricingStrategy.MARKET_BALANCE
    )

    return {
        "gpu_id": gpu.id,
        "status": "registered",
        "message": f"GPU {gpu.model} registered successfully",
        "base_price": base_price,
        "dynamic_price": initial_price,
        "pricing_strategy": "market_balance"
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
    gpus = session.execute(stmt).scalars().all()
    return [_gpu_to_dict(g) for g in gpus]


@router.get("/marketplace/gpu/{gpu_id}")
async def get_gpu_details(gpu_id: str, session: SessionDep) -> Dict[str, Any]:
    """Get GPU details."""
    gpu = _get_gpu_or_404(session, gpu_id)
    result = _gpu_to_dict(gpu)

    if gpu.status == "booked":
        booking = session.execute(
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
async def book_gpu(
    gpu_id: str, 
    request: GPUBookRequest, 
    session: SessionDep,
    engine: DynamicPricingEngine = Depends(get_pricing_engine)
) -> Dict[str, Any]:
    """Book a GPU with dynamic pricing."""
    gpu = _get_gpu_or_404(session, gpu_id)

    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is not available",
        )

    start_time = datetime.utcnow()
    end_time = start_time + timedelta(hours=request.duration_hours)
    
    # Calculate dynamic price at booking time
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=gpu_id,
            resource_type=ResourceType.GPU,
            base_price=gpu.price_per_hour,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu.region
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
        status="active"
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
        "pricing_factors": dynamic_result.factors_exposed if 'dynamic_result' in locals() else {},
        "confidence_score": dynamic_result.confidence_score if 'dynamic_result' in locals() else 0.8
    }


@router.post("/marketplace/gpu/{gpu_id}/release")
async def release_gpu(gpu_id: str, session: SessionDep) -> Dict[str, Any]:
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
        select(GPUBooking)
        .where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active")
        .limit(1)
    ).first()

    refund = 0.0
    if booking:
        try:
            refund = booking.total_cost * 0.5
            booking.status = "cancelled"
        except AttributeError as e:
            print(f"Warning: Booking missing attribute: {e}")
            refund = 0.0

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

    reviews = session.execute(
        select(GPUReview)
        .where(GPUReview.gpu_id == gpu_id)
        .order_by(GPUReview.created_at.desc())
    ).scalars().all()

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
    total_count = session.execute(
        select(func.count(GPUReview.id)).where(GPUReview.gpu_id == gpu_id)
    ).one()
    avg_rating = session.execute(
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

    bookings = session.execute(stmt).scalars().all()
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
async def get_pricing(
    model: str, 
    session: SessionDep,
    engine: DynamicPricingEngine = Depends(get_pricing_engine),
    collector: MarketDataCollector = Depends(get_market_collector)
) -> Dict[str, Any]:
    """Get enhanced pricing information for a model with dynamic pricing."""
    # SQLite JSON doesn't support array contains, so fetch all and filter in Python
    all_gpus = session.execute(select(GPURegistry)).scalars().all()
    compatible = [
        g for g in all_gpus
        if model.lower() in g.model.lower()
    ]

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
                region=gpu.region
            )
            dynamic_prices.append({
                "gpu_id": gpu.id,
                "static_price": gpu.price_per_hour,
                "dynamic_price": dynamic_result.recommended_price,
                "price_change": dynamic_result.recommended_price - gpu.price_per_hour,
                "price_change_percent": ((dynamic_result.recommended_price - gpu.price_per_hour) / gpu.price_per_hour) * 100,
                "confidence": dynamic_result.confidence_score,
                "trend": dynamic_result.price_trend.value,
                "reasoning": dynamic_result.reasoning
            })
        except Exception as e:
            # Fallback to static price if dynamic pricing fails
            dynamic_prices.append({
                "gpu_id": gpu.id,
                "static_price": gpu.price_per_hour,
                "dynamic_price": gpu.price_per_hour,
                "price_change": 0.0,
                "price_change_percent": 0.0,
                "confidence": 0.5,
                "trend": "unknown",
                "reasoning": ["Dynamic pricing unavailable"]
            })
    
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
                "confidence_score": market_data.confidence_score
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
            "avg_price_change_percent": ((avg_dynamic_price - (sum(static_prices) / len(static_prices))) / (sum(static_prices) / len(static_prices))) * 100,
            "gpus_with_price_increase": len([dp for dp in dynamic_prices if dp["price_change"] > 0]),
            "gpus_with_price_decrease": len([dp for dp in dynamic_prices if dp["price_change"] < 0]),
        },
        "individual_gpu_pricing": dynamic_prices,
        "market_analysis": market_analysis,
        "pricing_timestamp": datetime.utcnow().isoformat() + "Z"
    }
