"""Marketplace RPC endpoints for AITBC blockchain"""

from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from ..database import session_scope
from ..metrics import metrics_registry
from .router import router


class MarketplaceListing(BaseModel):
    """Marketplace listing model"""
    listing_id: Optional[str] = None
    seller_address: str = Field(..., description="Seller wallet address")
    item_type: str = Field(..., description="Type of item (GPU, compute, etc.)")
    price: float = Field(..., ge=0, description="Price in AIT")
    description: str = Field(..., description="Item description")
    status: str = Field(default="active", description="Listing status")
    created_at: Optional[datetime] = None

class MarketplaceCreateRequest(BaseModel):
    """Request to create marketplace listing"""
    seller_address: str
    item_type: str
    price: float
    description: str

# In-memory storage for demo (in production, use database)
_marketplace_listings: List[Dict[str, Any]] = [
    {
        "listing_id": "demo_001",
        "seller_address": "ait1demo_seller_123...",
        "item_type": "GPU",
        "price": 1000.0,
        "description": "High-performance NVIDIA RTX 4090 for AI training",
        "status": "active",
        "created_at": datetime.now().isoformat()
    },
    {
        "listing_id": "demo_002", 
        "seller_address": "ait1demo_provider_456...",
        "item_type": "Compute",
        "price": 500.0,
        "description": "10 hours of GPU compute time for deep learning",
        "status": "active",
        "created_at": datetime.now().isoformat()
    }
]

@router.get("/marketplace/listings", summary="List marketplace items", tags=["marketplace"])
async def marketplace_listings() -> Dict[str, Any]:
    """Get all marketplace listings"""
    try:
        metrics_registry.increment("rpc_marketplace_listings_total")
        
        # Filter active listings
        active_listings = [listing for listing in _marketplace_listings if listing.get("status") == "active"]
        
        return {
            "listings": active_listings,
            "total": len(active_listings),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_listings_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/marketplace/create", summary="Create marketplace listing", tags=["marketplace"])
async def marketplace_create(request: MarketplaceCreateRequest) -> Dict[str, Any]:
    """Create a new marketplace listing"""
    try:
        metrics_registry.increment("rpc_marketplace_create_total")
        
        # Generate unique listing ID
        listing_id = f"listing_{len(_marketplace_listings) + 1:03d}"
        
        # Create new listing
        new_listing = {
            "listing_id": listing_id,
            "seller_address": request.seller_address,
            "item_type": request.item_type,
            "price": request.price,
            "description": request.description,
            "status": "active",
            "created_at": datetime.now().isoformat()
        }
        
        # Add to storage
        _marketplace_listings.append(new_listing)
        
        return {
            "listing_id": listing_id,
            "status": "created",
            "message": "Marketplace listing created successfully",
            "listing": new_listing
        }
        
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_create_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/marketplace/listing/{listing_id}", summary="Get marketplace listing by ID", tags=["marketplace"])
async def marketplace_get_listing(listing_id: str) -> Dict[str, Any]:
    """Get a specific marketplace listing"""
    try:
        metrics_registry.increment("rpc_marketplace_get_total")
        
        # Find listing
        for listing in _marketplace_listings:
            if listing.get("listing_id") == listing_id:
                return {
                    "listing": listing,
                    "found": True
                }
        
        raise HTTPException(status_code=404, detail="Listing not found")
        
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_get_errors_total")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/marketplace/listing/{listing_id}", summary="Delete marketplace listing", tags=["marketplace"])
async def marketplace_delete_listing(listing_id: str) -> Dict[str, Any]:
    """Delete a marketplace listing"""
    try:
        metrics_registry.increment("rpc_marketplace_delete_total")
        
        # Find and remove listing
        for i, listing in enumerate(_marketplace_listings):
            if listing.get("listing_id") == listing_id:
                _marketplace_listings.pop(i)
                return {
                    "listing_id": listing_id,
                    "status": "deleted",
                    "message": "Marketplace listing deleted successfully"
                }
        
        raise HTTPException(status_code=404, detail="Listing not found")
        
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_delete_errors_total")
        raise HTTPException(status_code=500, detail=str(e))
