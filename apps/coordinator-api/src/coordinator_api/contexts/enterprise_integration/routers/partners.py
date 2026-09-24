"""
Partner Router - Third-party integration management
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from aitbc.rate_limiting import rate_limit

from ....storage import get_session
from ..domain.partner import Partner, PartnerWebhook

router = APIRouter(tags=["partners"])


class PartnerRegister(BaseModel):
    """Register a new partner application"""

    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)
    website: str = Field(..., pattern=r"^https?://")
    contact: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    integration_type: str = Field(..., pattern="^(explorer|analytics|wallet|exchange|other)$")


class PartnerResponse(BaseModel):
    """Partner registration response"""

    partner_id: str
    api_key: str
    api_secret: str
    rate_limit: dict[str, int]
    created_at: datetime


class WebhookCreate(BaseModel):
    """Create a webhook subscription"""

    url: str = Field(..., pattern=r"^https?://")
    events: list[str] = Field(..., min_length=1)
    secret: str | None = Field(default=None, max_length=100)


class WebhookResponse(BaseModel):
    """Webhook subscription response"""

    webhook_id: str
    url: str
    events: list[str]
    status: str
    created_at: datetime


RATE_LIMITS = {
    "explorer": {"requests_per_minute": 1000, "requests_per_hour": 50000},
    "analytics": {"requests_per_minute": 500, "requests_per_hour": 25000},
    "wallet": {"requests_per_minute": 100, "requests_per_hour": 5000},
    "exchange": {"requests_per_minute": 2000, "requests_per_hour": 100000},
    "other": {"requests_per_minute": 100, "requests_per_hour": 5000},
}

VALID_EVENTS = [
    "block.created",
    "transaction.confirmed",
    "market.offer_created",
    "market.bid_placed",
    "governance.proposal_created",
    "governance.vote_cast",
]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@router.post("/partners/register", response_model=PartnerResponse)
@rate_limit(rate=10, per=60)
async def register_partner(
    partner: PartnerRegister, request: Request, session: Annotated[Session, Depends(get_session)]
) -> PartnerResponse:
    """Register a new partner application"""

    # Generate credentials
    partner_id = secrets.token_urlsafe(16)
    api_key = f"aitbc_{secrets.token_urlsafe(24)}"
    api_secret = secrets.token_urlsafe(32)

    # Set rate limits based on integration type
    rate_limit = RATE_LIMITS.get(partner.integration_type, RATE_LIMITS["other"])

    # Store partner — only the hashes of the credentials are persisted
    row = Partner(
        id=partner_id,
        name=partner.name,
        description=partner.description,
        website=partner.website,
        contact=partner.contact,
        integration_type=partner.integration_type,
        api_key_hash=_hash(api_key),
        api_secret_hash=_hash(api_secret),
        rate_limit=rate_limit,
        status="active",
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()

    return PartnerResponse(
        partner_id=partner_id,
        api_key=api_key,
        api_secret=api_secret,
        rate_limit=rate_limit,
        created_at=row.created_at,
    )


@router.get("/partners/{partner_id}")
@rate_limit(rate=50, per=60)
async def get_partner(
    partner_id: str, request: Request, session: Annotated[Session, Depends(get_session)], api_key: str
) -> dict[str, Any]:
    """Get partner information"""

    # Verify API key
    partner = verify_partner_api_key(session, partner_id, api_key)
    if not partner:
        raise HTTPException(401, "Invalid credentials")

    # Return safe partner info
    return {
        "partner_id": partner.id,
        "name": partner.name,
        "integration_type": partner.integration_type,
        "rate_limit": partner.rate_limit,
        "created_at": partner.created_at,
        "status": partner.status,
    }


@router.post("/partners/webhooks", response_model=WebhookResponse)
@rate_limit(rate=20, per=60)
async def create_webhook(
    webhook: WebhookCreate, request: Request, session: Annotated[Session, Depends(get_session)], api_key: str
) -> WebhookResponse:
    """Create a webhook subscription"""

    # Verify partner from API key
    partner = find_partner_by_api_key(session, api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")

    # Validate events
    for event in webhook.events:
        if event not in VALID_EVENTS:
            raise HTTPException(400, f"Invalid event: {event}")

    # Generate webhook secret if not provided
    secret = webhook.secret or secrets.token_urlsafe(32)

    # Create webhook
    webhook_id = secrets.token_urlsafe(16)
    row = PartnerWebhook(
        id=webhook_id,
        partner_id=partner.id,
        url=webhook.url,
        events=webhook.events,
        secret=secret,
        status="active",
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()

    return WebhookResponse(
        webhook_id=webhook_id,
        url=row.url,
        events=row.events,
        status="active",
        created_at=row.created_at,
    )


@router.get("/partners/webhooks")
@rate_limit(rate=50, per=60)
async def list_webhooks(
    request: Request, session: Annotated[Session, Depends(get_session)], api_key: str
) -> list[WebhookResponse]:
    """List partner webhooks"""

    # Verify partner
    partner = find_partner_by_api_key(session, api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")

    # Get webhooks for partner
    rows = session.exec(select(PartnerWebhook).where(PartnerWebhook.partner_id == partner.id)).all()
    return [
        WebhookResponse(
            webhook_id=row.id,
            url=row.url,
            events=row.events,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/partners/webhooks/{webhook_id}")
@rate_limit(rate=20, per=60)
async def delete_webhook(
    webhook_id: str, request: Request, session: Annotated[Session, Depends(get_session)], api_key: str
) -> dict[str, str]:
    """Delete a webhook"""

    # Verify partner
    partner = find_partner_by_api_key(session, api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")

    # Find webhook
    webhook = session.get(PartnerWebhook, webhook_id)
    if not webhook or webhook.partner_id != partner.id:
        raise HTTPException(404, "Webhook not found")

    # Delete webhook
    session.delete(webhook)
    session.commit()

    return {"message": "Webhook deleted successfully"}


@router.get("/partners/analytics/usage")
@rate_limit(rate=30, per=60)
async def get_usage_analytics(
    request: Request, session: Annotated[Session, Depends(get_session)], api_key: str, period: str = "24h"
) -> dict[str, Any]:
    """Get API usage analytics"""

    # Verify partner
    partner = find_partner_by_api_key(session, api_key)
    if not partner:
        raise HTTPException(401, "Invalid API key")

    # Mock usage data (in production, query from analytics)
    usage = {
        "period": period,
        "requests": {"total": 15420, "blocks": 5000, "transactions": 8000, "market": 2000, "analytics": 420},
        "rate_limit": {"used": 15420, "limit": partner.rate_limit["requests_per_hour"], "percentage": 30.84},
        "errors": {"4xx": 12, "5xx": 3},
        "top_endpoints": [
            {"endpoint": "/blocks", "requests": 5000},
            {"endpoint": "/transactions", "requests": 8000},
            {"endpoint": "/market/offers", "requests": 2000},
        ],
    }

    return usage


# Helper functions


def verify_partner_api_key(session: Session, partner_id: str, api_key: str) -> Partner | None:
    """Verify partner credentials"""
    partner = session.get(Partner, partner_id)
    if not partner:
        return None

    # Check API key
    if not hmac.compare_digest(partner.api_key_hash, _hash(api_key)):
        return None

    return partner


def find_partner_by_api_key(session: Session, api_key: str) -> Partner | None:
    """Find partner by API key"""
    return session.exec(select(Partner).where(Partner.api_key_hash == _hash(api_key))).first()


# Export the router
__all__ = ["router"]
