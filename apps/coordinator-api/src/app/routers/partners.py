"""
Partner Router - Third-party integration management
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import secrets
import hashlib

from ..schemas import UserProfile
from ..storage import SessionDep
from sqlmodel import select

router = APIRouter(tags=["partners"])


class PartnerRegister(BaseModel):
    """Register a new partner application"""
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)
    website: str = Field(..., pattern=r'^https?://')
    contact: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    integration_type: str = Field(..., pattern="^(explorer|analytics|wallet|exchange|other)$")


class PartnerResponse(BaseModel):
    """Partner registration response"""
    partner_id: str
    api_key: str
    api_secret: str
    rate_limit: Dict[str, int]
    created_at: datetime


class WebhookCreate(BaseModel):
    """Create a webhook subscription"""
    url: str = Field(..., pattern=r'^https?://')
    events: List[str] = Field(..., min_items=1)
    secret: Optional[str] = Field(max_length=100)


class WebhookResponse(BaseModel):
    """Webhook subscription response"""
    webhook_id: str
    url: str
    events: List[str]
    status: str
    created_at: datetime


# Mock partner storage (in production, use database)
PARTNERS_DB = {}
WEBHOOKS_DB = {}


@router.post("/partners/register", response_model=PartnerResponse)
async def register_partner(
    partner: PartnerRegister,
    session: SessionDep
) -> PartnerResponse:
    """Register a new partner application"""
    
    # Generate credentials
    partner_id = secrets.token_urlsafe(16)
    api_key = f"aitbc_{secrets.token_urlsafe(24)}"
    api_secret = secrets.token_urlsafe(32)
    
    # Set rate limits based on integration type
    rate_limits = {
        "explorer": {"requests_per_minute": 1000, "requests_per_hour": 50000},
        "analytics": {"requests_per_minute": 500, "requests_per_hour": 25000},
        "wallet": {"requests_per_minute": 100, "requests_per_hour": 5000},
        "exchange": {"requests_per_minute": 2000, "requests_per_hour": 100000},
        "other": {"requests_per_minute": 100, "requests_per_hour": 5000}
    }
    
    # Store partner (in production, save to database)
    PARTNERS_DB[partner_id] = {
        "id": partner_id,
        "name": partner.name,
        "description": partner.description,
        "website": partner.website,
        "contact": partner.contact,
        "integration_type": partner.integration_type,
        "api_key": api_key,
        "api_secret_hash": hashlib.sha256(api_secret.encode()).hexdigest(),
        "rate_limit": rate_limits.get(partner.integration_type, rate_limits["other"]),
        "created_at": datetime.utcnow(),
        "status": "active"
    }
    
    return PartnerResponse(
        partner_id=partner_id,
        api_key=api_key,
        api_secret=api_secret,
        rate_limit=PARTNERS_DB[partner_id]["rate_limit"],
        created_at=PARTNERS_DB[partner_id]["created_at"]
    )


@router.get("/partners/{partner_id}")
async def get_partner(
    partner_id: str,
    session: SessionDep,
    api_key: str
) -> Dict[str, Any]:
    """Get partner information"""
    
    # Verify API key
    partner = verify_partner_api_key(partner_id, api_key)
    if not partner:
        raise HTTPException(401, "Invalid credentials")
    
    # Return safe partner info
    return {
        "partner_id": partner["id"],
        "name": partner["name"],
        "integration_type": partner["integration_type"],
        "rate_limit": partner["rate_limit"],
        "created_at": partner["created_at"],
        "status": partner["status"]
    }


@router.post("/partners/webhooks", response_model=WebhookResponse)
async def create_webhook(
    webhook: WebhookCreate,
    session: SessionDep,
    api_key: str
) -> WebhookResponse:
    """Create a webhook subscription"""
    
    # Verify partner from API key
    partner = find_partner_by_api_key(api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")
    
    # Validate events
    valid_events = [
        "block.created",
        "transaction.confirmed",
        "marketplace.offer_created",
        "marketplace.bid_placed",
        "governance.proposal_created",
        "governance.vote_cast"
    ]
    
    for event in webhook.events:
        if event not in valid_events:
            raise HTTPException(400, f"Invalid event: {event}")
    
    # Generate webhook secret if not provided
    if not webhook.secret:
        webhook.secret = secrets.token_urlsafe(32)
    
    # Create webhook
    webhook_id = secrets.token_urlsafe(16)
    WEBHOOKS_DB[webhook_id] = {
        "id": webhook_id,
        "partner_id": partner["id"],
        "url": webhook.url,
        "events": webhook.events,
        "secret": webhook.secret,
        "status": "active",
        "created_at": datetime.utcnow()
    }
    
    return WebhookResponse(
        webhook_id=webhook_id,
        url=webhook.url,
        events=webhook.events,
        status="active",
        created_at=WEBHOOKS_DB[webhook_id]["created_at"]
    )


@router.get("/partners/webhooks")
async def list_webhooks(
    session: SessionDep,
    api_key: str
) -> List[WebhookResponse]:
    """List partner webhooks"""
    
    # Verify partner
    partner = find_partner_by_api_key(api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")
    
    # Get webhooks for partner
    webhooks = []
    for webhook in WEBHOOKS_DB.values():
        if webhook["partner_id"] == partner["id"]:
            webhooks.append(WebhookResponse(
                webhook_id=webhook["id"],
                url=webhook["url"],
                events=webhook["events"],
                status=webhook["status"],
                created_at=webhook["created_at"]
            ))
    
    return webhooks


@router.delete("/partners/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    session: SessionDep,
    api_key: str
) -> Dict[str, str]:
    """Delete a webhook"""
    
    # Verify partner
    partner = find_partner_by_api_key(api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")
    
    # Find webhook
    webhook = WEBHOOKS_DB.get(webhook_id)
    if not webhook or webhook["partner_id"] != partner["id"]:
        raise HTTPException(404, "Webhook not found")
    
    # Delete webhook
    del WEBHOOKS_DB[webhook_id]
    
    return {"message": "Webhook deleted successfully"}


@router.get("/partners/analytics/usage")
async def get_usage_analytics(
    session: SessionDep,
    api_key: str,
    period: str = "24h"
) -> Dict[str, Any]:
    """Get API usage analytics"""
    
    # Verify partner
    partner = find_partner_by_api_key(api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")
    
    # Mock usage data (in production, query from analytics)
    usage = {
        "period": period,
        "requests": {
            "total": 15420,
            "blocks": 5000,
            "transactions": 8000,
            "marketplace": 2000,
            "analytics": 420
        },
        "rate_limit": {
            "used": 15420,
            "limit": partner["rate_limit"]["requests_per_hour"],
            "percentage": 30.84
        },
        "errors": {
            "4xx": 12,
            "5xx": 3
        },
        "top_endpoints": [
            { "endpoint": "/blocks", "requests": 5000 },
            { "endpoint": "/transactions", "requests": 8000 },
            { "endpoint": "/marketplace/offers", "requests": 2000 }
        ]
    }
    
    return usage


# Helper functions

def verify_partner_api_key(partner_id: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Verify partner credentials"""
    partner = PARTNERS_DB.get(partner_id)
    if not partner:
        return None
    
    # Check API key
    if partner["api_key"] != api_key:
        return None
    
    return partner


def find_partner_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Find partner by API key"""
    for partner in PARTNERS_DB.values():
        if partner["api_key"] == api_key:
            return partner
    return None


# Export the router
__all__ = ["router"]
