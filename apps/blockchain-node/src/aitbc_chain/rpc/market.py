"""Market RPC endpoints for AITBC blockchain"""

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

# In-memory storage for market listings
_market_listings: list[dict[str, Any]] = []


async def _publish_offer_event(
    event_type: str, offer_id: str, chain_id: str, offer_data: dict[str, Any] | None = None
) -> None:
    """Publish an offer change event to the gossip topic ``offers.{chain_id}``.

    This is the v0.8.2 §B9 integration point — on market listing
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


class MarketListing(BaseModel):
    """Market listing model"""

    listing_id: str | None = None
    seller_address: str = Field(..., description="Seller wallet address")
    item_type: str = Field(..., description="Type of item (GPU, compute, etc.)")
    # not-money: wire format. This mirrors the "price" key inside a GPU_MARKET
    # transaction payload (read at market_listings below), which is json.dumps'd
    # and keccak-hashed for signature verification. Decimal is not JSON-serializable,
    # and "0.5" != 0.5 would invalidate signatures already on chain. Hard fork -- see
    # docs/architecture/money-types-and-the-signature-boundary.md.
    price: float = Field(..., ge=0, description="Price in AIT")
    description: str = Field(..., description="Item description")
    status: str = Field(default="active", description="Listing status")
    created_at: datetime | None = None
    gpu_name: str | None = Field(default=None, description="GPU name from nvidia-smi")
    gpu_device: str | None = Field(default=None, description="GPU device index")
    gpu_uuid: str | None = Field(default=None, description="Physical GPU UUID")
    gpu_model: str | None = Field(default=None, description="GPU model name")
    memory_gb: int | None = Field(default=None, description="GPU memory in GB")
    compute_capability: str | None = Field(default=None, description="CUDA compute capability")


class MarketCreateRequest(BaseModel):
    """Request to create market listing"""

    seller_address: str
    item_type: str
    # not-money: becomes the price field of a listing in the wire format above
    price: float
    description: str
    gpu_name: str | None = None
    gpu_device: str | None = None
    gpu_uuid: str | None = None
    gpu_model: str | None = None
    memory_gb: int | None = None
    compute_capability: str | None = None


@router.get("/market/listings", summary="List market items", tags=["market"])
async def market_listings() -> dict[str, Any]:
    """Get all market listings from blockchain"""
    try:
        metrics_registry.increment("rpc_market_listings_total")

        # Read GPU_MARKET transactions from blockchain
        import sqlite3
        import os
        from pathlib import Path

        chain_db_path = Path(f"/var/lib/aitbc/data/{os.environ.get('CHAIN_ID', 'ait-localnet')}/chain.db")
        if not chain_db_path.exists():
            chain_db_path = Path("/var/lib/aitbc/data/chain.db")

        listings = []
        if chain_db_path.exists():
            conn = sqlite3.connect(str(chain_db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sender, payload, timestamp FROM \"transaction\" WHERE type = 'GPU_MARKET' AND status = 'confirmed' ORDER BY timestamp DESC"
            )
            rows = cursor.fetchall()
            conn.close()

            cancelled_ids: set[str] = set()
            offer_rows: list[tuple[Any, ...]] = []

            for tx_id, sender, payload_json, timestamp in rows:
                try:
                    payload = json.loads(payload_json) if payload_json else {}
                    action = payload.get("action", "")
                    order_id = payload.get("order_id", "")
                    order_ids = payload.get("order_ids") or []
                    if not isinstance(order_ids, list):
                        order_ids = [order_ids]
                    replaces = payload.get("replaces") or []
                    if not isinstance(replaces, list):
                        replaces = [replaces]
                    listing_id = f"tx_{tx_id}"
                    if action in ("cancel", "cancelled") or str(payload.get("status", "")).lower() == "cancelled":
                        if order_id:
                            cancelled_ids.add(order_id)
                        cancelled_ids.update(str(oid) for oid in order_ids)
                        cancelled_ids.add(listing_id)
                        continue
                    cancelled_ids.update(str(r) for r in replaces)
                    offer_rows.append((tx_id, sender, payload, timestamp))
                except json.JSONDecodeError:
                    continue

            for tx_id, sender, payload, timestamp in offer_rows:
                listing_id = f"tx_{tx_id}"
                if listing_id in cancelled_ids:
                    continue
                listing = {
                    "listing_id": listing_id,
                    "seller_address": sender,
                    "provider_address": payload.get("provider_address") or sender,
                    "service_type": payload.get("service_type", ""),
                    "model": payload.get("model", ""),
                    "item_type": payload.get("item_type", "GPU"),
                    "price": payload.get("price", 0.0),
                    "price_unit": payload.get("price_unit", ""),
                    "description": payload.get("description", ""),
                    "deployment_type": payload.get("deployment_type", ""),
                    "gpu_name": payload.get("gpu_name", ""),
                    "gpu_device": payload.get("gpu_device", ""),
                    "gpu_uuid": payload.get("gpu_uuid", ""),
                    "gpu_model": payload.get("gpu_model") or payload.get("gpu_name", ""),
                    "memory_gb": payload.get("memory_gb"),
                    "disk_quota_mb": payload.get("disk_quota_mb"),
                    "compute_capability": payload.get("compute_capability", ""),
                    "endpoint": payload.get("endpoint", ""),
                    "status": "active",
                    "created_at": timestamp or datetime.now().isoformat(),
                }
                listings.append(listing)

        # Merge on-chain listings with in-memory listings
        listings.extend(_market_listings)

        return {"listings": listings, "total": len(listings), "timestamp": datetime.now().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_market_listings_errors_total")
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/market/create", summary="Create market listing", tags=["market"])
async def market_create(request: MarketCreateRequest) -> dict[str, Any]:
    """Create a new market listing"""
    try:
        metrics_registry.increment("rpc_market_create_total")

        # Security validation: validate amount
        if not SecurityValidator.validate_amount(request.price):
            security_auditor.log_event(
                action="market_create_invalid_amount", details={"price": request.price}, severity="WARNING"
            )
            raise HTTPException(status_code=400, detail="Invalid price: must be a non-negative number")

        # Sanitize description
        description = SecurityValidator.sanitize_html(request.description)

        security_auditor.log_event(
            action="market_listing_created",
            details={"seller_address": request.seller_address, "item_type": request.item_type, "price": request.price},
            severity="INFO",
        )

        # Generate unique listing ID
        listing_id = f"listing_{len(_market_listings) + 1:03d}"

        # Create new listing
        new_listing = {
            "listing_id": listing_id,
            "seller_address": request.seller_address,
            "item_type": request.item_type,
            "price": request.price,
            "description": description,
            "gpu_name": request.gpu_name,
            "gpu_device": request.gpu_device,
            "gpu_uuid": request.gpu_uuid,
            "gpu_model": request.gpu_model or request.gpu_name,
            "memory_gb": request.memory_gb,
            "compute_capability": request.compute_capability,
            "status": "active",
            "created_at": datetime.now().isoformat(),
        }

        # Add to storage
        _market_listings.append(new_listing)

        # Publish offer created event to gossip (v0.8.2 §B9)
        await _publish_offer_event("created", listing_id, settings.chain_id, new_listing)

        return {
            "listing_id": listing_id,
            "status": "created",
            "message": "Market listing created successfully",
            "listing": new_listing,
        }

    except Exception as e:
        metrics_registry.increment("rpc_market_create_errors_total")
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/market/listing/{listing_id}", summary="Get market listing by ID", tags=["market"])
async def market_get_listing(listing_id: str) -> dict[str, Any]:
    """Get a specific market listing"""
    try:
        metrics_registry.increment("rpc_market_get_total")

        # Find listing
        for listing in _market_listings:
            if listing.get("listing_id") == listing_id:
                return {"listing": listing, "found": True}

        raise HTTPException(status_code=404, detail="Listing not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_market_get_errors_total")
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/market/listing/{listing_id}", summary="Delete market listing", tags=["market"])
async def market_delete_listing(listing_id: str) -> dict[str, Any]:
    """Delete a market listing"""
    try:
        metrics_registry.increment("rpc_market_delete_total")

        # Find and remove listing
        for i, listing in enumerate(_market_listings):
            if listing.get("listing_id") == listing_id:
                _market_listings.pop(i)
                # Publish offer deleted event to gossip (v0.8.2 §B9)
                await _publish_offer_event("deleted", listing_id, settings.chain_id)
                return {"listing_id": listing_id, "status": "deleted", "message": "Market listing deleted successfully"}

        raise HTTPException(status_code=404, detail="Listing not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_market_delete_errors_total")
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
