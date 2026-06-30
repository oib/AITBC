"""Marketplace RPC endpoints for AITBC blockchain"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aitbc.security import SecurityAuditor, SecurityValidator

from ..config import settings
from ..metrics import metrics_registry

router = APIRouter()
logger = logging.getLogger(__name__)

# Security auditor for logging
security_auditor = SecurityAuditor()

# In-memory storage for marketplace listings
_marketplace_listings: list[dict[str, Any]] = []


async def _publish_offer_event(
    event_type: str, offer_id: str, chain_id: str, offer_data: dict[str, Any] | None = None
) -> None:
    """Publish an offer change event to the gossip topic ``offers.{chain_id}``.

    This is the v0.8.2 §B9 integration point — on marketplace listing
    create/update/delete, an ``OfferEvent`` is published to the gossip
    broker so that trading services subscribed to ``offers.{chain_id}``
    receive real-time notifications.
    """
    try:
        from ..gossip import gossip_broker

        event: dict[str, Any] = {
            "event_type": event_type,
            "offer_id": offer_id,
            "chain_id": chain_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "blockchain-node",
        }
        if offer_data is not None:
            event["offer"] = offer_data
        else:
            event["offer"] = None
        topic = f"offers.{chain_id}"
        await gossip_broker.publish(topic, event)
        logger.debug("Published offer event %s for offer %s to topic %s", event_type, offer_id, topic)
    except Exception as e:
        logger.warning("Failed to publish offer event: %s", e)


class MarketplaceListing(BaseModel):
    """Marketplace listing model"""

    listing_id: str | None = None
    seller_address: str = Field(..., description="Seller wallet address")
    item_type: str = Field(..., description="Type of item (GPU, compute, etc.)")
    price: float = Field(..., ge=0, description="Price in AIT")
    description: str = Field(..., description="Item description")
    status: str = Field(default="active", description="Listing status")
    created_at: datetime | None = None


class MarketplaceCreateRequest(BaseModel):
    """Request to create marketplace listing"""

    seller_address: str
    item_type: str
    price: float
    description: str


@router.get("/marketplace/listings", summary="List marketplace items", tags=["marketplace"])
async def marketplace_listings() -> dict[str, Any]:
    """Get all marketplace listings from blockchain"""
    try:
        metrics_registry.increment("rpc_marketplace_listings_total")

        # Read GPU_MARKETPLACE transactions from blockchain
        import sqlite3
        from pathlib import Path

        chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        listings = []
        if chain_db_path.exists():
            conn = sqlite3.connect(str(chain_db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sender, payload, timestamp FROM \"transaction\" WHERE type = 'GPU_MARKETPLACE' AND status = 'confirmed' ORDER BY timestamp DESC"
            )
            rows = cursor.fetchall()
            conn.close()

            for tx_id, sender, payload_json, timestamp in rows:
                try:
                    payload = json.loads(payload_json) if payload_json else {}
                    listing = {
                        "listing_id": f"tx_{tx_id}",
                        "seller_address": sender,
                        "item_type": payload.get("item_type", "GPU"),
                        "price": payload.get("price", 0.0),
                        "description": payload.get("description", ""),
                        "status": "active",
                        "created_at": timestamp or datetime.now().isoformat(),
                    }
                    listings.append(listing)
                except json.JSONDecodeError:
                    continue

        return {"listings": listings, "total": len(listings), "timestamp": datetime.now().isoformat()}
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_listings_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/marketplace/create", summary="Create marketplace listing", tags=["marketplace"])
async def marketplace_create(request: MarketplaceCreateRequest) -> dict[str, Any]:
    """Create a new marketplace listing"""
    try:
        metrics_registry.increment("rpc_marketplace_create_total")

        # Security validation: validate amount
        if not SecurityValidator.validate_amount(request.price):
            security_auditor.log_event(
                action="marketplace_create_invalid_amount", details={"price": request.price}, severity="WARNING"
            )
            raise HTTPException(status_code=400, detail="Invalid price: must be a non-negative number")

        # Sanitize description
        description = SecurityValidator.sanitize_html(request.description)

        security_auditor.log_event(
            action="marketplace_listing_created",
            details={"seller_address": request.seller_address, "item_type": request.item_type, "price": request.price},
            severity="INFO",
        )

        # Generate unique listing ID
        listing_id = f"listing_{len(_marketplace_listings) + 1:03d}"

        # Create new listing
        new_listing = {
            "listing_id": listing_id,
            "seller_address": request.seller_address,
            "item_type": request.item_type,
            "price": request.price,
            "description": description,
            "status": "active",
            "created_at": datetime.now().isoformat(),
        }

        # Add to storage
        _marketplace_listings.append(new_listing)

        # Publish offer created event to gossip (v0.8.2 §B9)
        await _publish_offer_event("created", listing_id, settings.chain_id, new_listing)

        return {
            "listing_id": listing_id,
            "status": "created",
            "message": "Marketplace listing created successfully",
            "listing": new_listing,
        }

    except Exception as e:
        metrics_registry.increment("rpc_marketplace_create_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/marketplace/listing/{listing_id}", summary="Get marketplace listing by ID", tags=["marketplace"])
async def marketplace_get_listing(listing_id: str) -> dict[str, Any]:
    """Get a specific marketplace listing"""
    try:
        metrics_registry.increment("rpc_marketplace_get_total")

        # Find listing
        for listing in _marketplace_listings:
            if listing.get("listing_id") == listing_id:
                return {"listing": listing, "found": True}

        raise HTTPException(status_code=404, detail="Listing not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_get_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/marketplace/listing/{listing_id}", summary="Delete marketplace listing", tags=["marketplace"])
async def marketplace_delete_listing(listing_id: str) -> dict[str, Any]:
    """Delete a marketplace listing"""
    try:
        metrics_registry.increment("rpc_marketplace_delete_total")

        # Find and remove listing
        for i, listing in enumerate(_marketplace_listings):
            if listing.get("listing_id") == listing_id:
                _marketplace_listings.pop(i)
                # Publish offer deleted event to gossip (v0.8.2 §B9)
                await _publish_offer_event("deleted", listing_id, settings.chain_id)
                return {"listing_id": listing_id, "status": "deleted", "message": "Marketplace listing deleted successfully"}

        raise HTTPException(status_code=404, detail="Listing not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_delete_errors_total")
        raise HTTPException(status_code=500, detail=str(e)) from e
