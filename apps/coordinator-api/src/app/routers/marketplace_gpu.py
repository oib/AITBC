"""
GPU-specific marketplace endpoints to support CLI commands
Quick implementation with mock data to make CLI functional
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field

from ..storage import SessionDep

router = APIRouter(tags=["marketplace-gpu"])

# In-memory storage for bookings (quick fix)
gpu_bookings: Dict[str, Dict] = {}
gpu_reviews: Dict[str, List[Dict]] = {}
gpu_counter = 1

# Mock GPU data
mock_gpus = [
    {
        "id": "gpu_001",
        "miner_id": "miner_001",
        "model": "RTX 4090",
        "memory_gb": 24,
        "cuda_version": "12.0",
        "region": "us-west",
        "price_per_hour": 0.50,
        "status": "available",
        "capabilities": ["llama2-7b", "stable-diffusion-xl", "gpt-j"],
        "created_at": "2025-12-28T10:00:00Z",
        "average_rating": 4.5,
        "total_reviews": 12
    },
    {
        "id": "gpu_002",
        "miner_id": "miner_002",
        "model": "RTX 3080",
        "memory_gb": 16,
        "cuda_version": "11.8",
        "region": "us-east",
        "price_per_hour": 0.35,
        "status": "available",
        "capabilities": ["llama2-13b", "gpt-j"],
        "created_at": "2025-12-28T09:30:00Z",
        "average_rating": 4.2,
        "total_reviews": 8
    },
    {
        "id": "gpu_003",
        "miner_id": "miner_003",
        "model": "A100",
        "memory_gb": 40,
        "cuda_version": "12.0",
        "region": "eu-west",
        "price_per_hour": 1.20,
        "status": "booked",
        "capabilities": ["gpt-4", "claude-2", "llama2-70b"],
        "created_at": "2025-12-28T08:00:00Z",
        "average_rating": 4.8,
        "total_reviews": 25
    }
]

# Initialize some reviews
gpu_reviews = {
    "gpu_001": [
        {"rating": 5, "comment": "Excellent performance!", "user": "client_001", "date": "2025-12-27"},
        {"rating": 4, "comment": "Good value for money", "user": "client_002", "date": "2025-12-26"}
    ],
    "gpu_002": [
        {"rating": 4, "comment": "Solid GPU for smaller models", "user": "client_003", "date": "2025-12-27"}
    ],
    "gpu_003": [
        {"rating": 5, "comment": "Perfect for large models", "user": "client_004", "date": "2025-12-27"},
        {"rating": 5, "comment": "Fast and reliable", "user": "client_005", "date": "2025-12-26"}
    ]
}


class GPURegisterRequest(BaseModel):
    miner_id: str
    model: str
    memory_gb: int
    cuda_version: str
    region: str
    price_per_hour: float
    capabilities: List[str]


class GPUBookRequest(BaseModel):
    duration_hours: float
    job_id: Optional[str] = None


class GPUReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str


@router.post("/marketplace/gpu/register")
async def register_gpu(
    request: Dict[str, Any],
    session: SessionDep
) -> Dict[str, Any]:
    """Register a GPU in the marketplace"""
    global gpu_counter
    
    # Extract GPU specs from the request
    gpu_specs = request.get("gpu", {})
    
    gpu_id = f"gpu_{gpu_counter:03d}"
    gpu_counter += 1
    
    new_gpu = {
        "id": gpu_id,
        "miner_id": gpu_specs.get("miner_id", f"miner_{gpu_counter:03d}"),
        "model": gpu_specs.get("name", "Unknown GPU"),
        "memory_gb": gpu_specs.get("memory", 0),
        "cuda_version": gpu_specs.get("cuda_version", "Unknown"),
        "region": gpu_specs.get("region", "unknown"),
        "price_per_hour": gpu_specs.get("price_per_hour", 0.0),
        "status": "available",
        "capabilities": gpu_specs.get("capabilities", []),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "average_rating": 0.0,
        "total_reviews": 0
    }
    
    mock_gpus.append(new_gpu)
    gpu_reviews[gpu_id] = []
    
    return {
        "gpu_id": gpu_id,
        "status": "registered",
        "message": f"GPU {gpu_specs.get('name', 'Unknown')} registered successfully"
    }


@router.get("/marketplace/gpu/list")
async def list_gpus(
    available: Optional[bool] = Query(default=None),
    price_max: Optional[float] = Query(default=None),
    region: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
) -> List[Dict[str, Any]]:
    """List available GPUs"""
    filtered_gpus = mock_gpus.copy()
    
    # Apply filters
    if available is not None:
        filtered_gpus = [g for g in filtered_gpus if g["status"] == ("available" if available else "booked")]
    
    if price_max is not None:
        filtered_gpus = [g for g in filtered_gpus if g["price_per_hour"] <= price_max]
    
    if region:
        filtered_gpus = [g for g in filtered_gpus if g["region"].lower() == region.lower()]
    
    if model:
        filtered_gpus = [g for g in filtered_gpus if model.lower() in g["model"].lower()]
    
    return filtered_gpus[:limit]


@router.get("/marketplace/gpu/{gpu_id}")
async def get_gpu_details(gpu_id: str) -> Dict[str, Any]:
    """Get GPU details"""
    gpu = next((g for g in mock_gpus if g["id"] == gpu_id), None)
    
    if not gpu:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"GPU {gpu_id} not found"
        )
    
    # Add booking info if booked
    if gpu["status"] == "booked" and gpu_id in gpu_bookings:
        gpu["current_booking"] = gpu_bookings[gpu_id]
    
    return gpu


@router.post("/marketplace/gpu/{gpu_id}/book", status_code=http_status.HTTP_201_CREATED)
async def book_gpu(gpu_id: str, request: GPUBookRequest) -> Dict[str, Any]:
    """Book a GPU"""
    gpu = next((g for g in mock_gpus if g["id"] == gpu_id), None)
    
    if not gpu:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"GPU {gpu_id} not found"
        )
    
    if gpu["status"] != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is not available"
        )
    
    # Create booking
    booking_id = f"booking_{gpu_id}_{int(datetime.utcnow().timestamp())}"
    start_time = datetime.utcnow()
    end_time = start_time + timedelta(hours=request.duration_hours)
    
    booking = {
        "booking_id": booking_id,
        "gpu_id": gpu_id,
        "duration_hours": request.duration_hours,
        "job_id": request.job_id,
        "start_time": start_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
        "total_cost": request.duration_hours * gpu["price_per_hour"],
        "status": "active"
    }
    
    # Update GPU status
    gpu["status"] = "booked"
    gpu_bookings[gpu_id] = booking
    
    return {
        "booking_id": booking_id,
        "gpu_id": gpu_id,
        "status": "booked",
        "total_cost": booking["total_cost"],
        "start_time": booking["start_time"],
        "end_time": booking["end_time"]
    }


@router.post("/marketplace/gpu/{gpu_id}/release")
async def release_gpu(gpu_id: str) -> Dict[str, Any]:
    """Release a booked GPU"""
    gpu = next((g for g in mock_gpus if g["id"] == gpu_id), None)
    
    if not gpu:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"GPU {gpu_id} not found"
        )
    
    if gpu["status"] != "booked":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"GPU {gpu_id} is not booked"
        )
    
    # Get booking info for refund calculation
    booking = gpu_bookings.get(gpu_id, {})
    refund = 0.0
    
    if booking:
        # Calculate refund (simplified - 50% if released early)
        refund = booking.get("total_cost", 0.0) * 0.5
        del gpu_bookings[gpu_id]
    
    # Update GPU status
    gpu["status"] = "available"
    
    return {
        "status": "released",
        "gpu_id": gpu_id,
        "refund": refund,
        "message": f"GPU {gpu_id} released successfully"
    }


@router.get("/marketplace/gpu/{gpu_id}/reviews")
async def get_gpu_reviews(
    gpu_id: str,
    limit: int = Query(default=10, ge=1, le=100)
) -> Dict[str, Any]:
    """Get GPU reviews"""
    gpu = next((g for g in mock_gpus if g["id"] == gpu_id), None)
    
    if not gpu:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"GPU {gpu_id} not found"
        )
    
    reviews = gpu_reviews.get(gpu_id, [])
    
    return {
        "gpu_id": gpu_id,
        "average_rating": gpu["average_rating"],
        "total_reviews": gpu["total_reviews"],
        "reviews": reviews[:limit]
    }


@router.post("/marketplace/gpu/{gpu_id}/reviews", status_code=http_status.HTTP_201_CREATED)
async def add_gpu_review(gpu_id: str, request: GPUReviewRequest) -> Dict[str, Any]:
    """Add a review for a GPU"""
    gpu = next((g for g in mock_gpus if g["id"] == gpu_id), None)
    
    if not gpu:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"GPU {gpu_id} not found"
        )
    
    # Add review
    review = {
        "rating": request.rating,
        "comment": request.comment,
        "user": "current_user",  # Would get from auth context
        "date": datetime.utcnow().isoformat() + "Z"
    }
    
    if gpu_id not in gpu_reviews:
        gpu_reviews[gpu_id] = []
    
    gpu_reviews[gpu_id].append(review)
    
    # Update average rating
    all_reviews = gpu_reviews[gpu_id]
    gpu["average_rating"] = sum(r["rating"] for r in all_reviews) / len(all_reviews)
    gpu["total_reviews"] = len(all_reviews)
    
    return {
        "status": "review_added",
        "gpu_id": gpu_id,
        "review_id": f"review_{len(all_reviews)}",
        "average_rating": gpu["average_rating"]
    }


@router.get("/marketplace/orders")
async def list_orders(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
) -> List[Dict[str, Any]]:
    """List orders (bookings)"""
    orders = []
    
    for gpu_id, booking in gpu_bookings.items():
        gpu = next((g for g in mock_gpus if g["id"] == gpu_id), None)
        if gpu:
            order = {
                "order_id": booking["booking_id"],
                "gpu_id": gpu_id,
                "gpu_model": gpu["model"],
                "miner_id": gpu["miner_id"],
                "duration_hours": booking["duration_hours"],
                "total_cost": booking["total_cost"],
                "status": booking["status"],
                "created_at": booking["start_time"],
                "job_id": booking.get("job_id")
            }
            orders.append(order)
    
    if status:
        orders = [o for o in orders if o["status"] == status]
    
    return orders[:limit]


@router.get("/marketplace/pricing/{model}")
async def get_pricing(model: str) -> Dict[str, Any]:
    """Get pricing information for a model"""
    # Find GPUs that support this model
    compatible_gpus = [
        gpu for gpu in mock_gpus
        if any(model.lower() in cap.lower() for cap in gpu["capabilities"])
    ]
    
    if not compatible_gpus:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No GPUs found for model {model}"
        )
    
    prices = [gpu["price_per_hour"] for gpu in compatible_gpus]
    
    return {
        "model": model,
        "min_price": min(prices),
        "max_price": max(prices),
        "average_price": sum(prices) / len(prices),
        "available_gpus": len([g for g in compatible_gpus if g["status"] == "available"]),
        "total_gpus": len(compatible_gpus),
        "recommended_gpu": min(compatible_gpus, key=lambda x: x["price_per_hour"])["id"]
    }
