"\nEnhanced Marketplace API Router - Simplified Version\nREST API endpoints for enhanced marketplace features\n"
from typing import Annotated, Any

from aitbc import get_logger

logger = get_logger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlmodel import Session  # noqa: E402

from aitbc.rate_limiting import rate_limit  # noqa: E402

from ..contexts.marketplace.services.marketplace_enhanced_simple import (  # noqa: E402
    EnhancedMarketplaceService,
    LicenseType,
    VerificationType,
)
from ..deps import require_admin_key  # noqa: E402
from ..storage import get_session  # noqa: E402

router = APIRouter(prefix="/marketplace/enhanced", tags=["Marketplace Enhanced"])


class RoyaltyDistributionRequest(BaseModel):
    """Request for creating royalty distribution"""

    tiers: dict[str, float] = Field(..., description="Royalty tiers and percentages")
    dynamic_rates: bool = Field(default=False, description="Enable dynamic royalty rates")


class ModelLicenseRequest(BaseModel):
    """Request for creating model license"""

    license_type: LicenseType = Field(..., description="Type of license")
    terms: dict[str, Any] = Field(..., description="License terms and conditions")
    usage_rights: list[str] = Field(..., description="List of usage rights")
    custom_terms: dict[str, Any] | None = Field(default=None, description="Custom license terms")


class ModelVerificationRequest(BaseModel):
    """Request for model verification"""

    verification_type: VerificationType = Field(default=VerificationType.COMPREHENSIVE, description="Type of verification")


class MarketplaceAnalyticsRequest(BaseModel):
    """Request for marketplace analytics"""

    period_days: int = Field(default=30, description="Period in days for analytics")
    metrics: list[str] | None = Field(default=None, description="Specific metrics to retrieve")


@router.post("/royalty/create")
@rate_limit(rate=20, per=60)
async def create_royalty_distribution(
    request: Request,
    royalty_request: RoyaltyDistributionRequest,
    offer_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Create royalty distribution for marketplace offer"""
    try:
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        result = await enhanced_service.create_royalty_distribution(
            offer_id=offer_id, royalty_tiers=request.tiers, dynamic_rates=request.dynamic_rates
        )  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error("Error creating royalty distribution: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/royalty/calculate/{offer_id}")
@rate_limit(rate=50, per=60)
async def calculate_royalties(
    request: Request,
    offer_id: str,
    sale_amount: float,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Calculate royalties for a sale"""
    try:
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        royalties = await enhanced_service.calculate_royalties(offer_id=offer_id, sale_amount=sale_amount)
        return royalties
    except Exception as e:
        logger.error("Error calculating royalties: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/license/create")
@rate_limit(rate=20, per=60)
async def create_model_license(
    request: Request,
    license_request: ModelLicenseRequest,
    offer_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Create model license for marketplace offer"""
    try:
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        result = await enhanced_service.create_model_license(
            offer_id=offer_id,
            license_type=request.license_type,
            terms=request.terms,
            usage_rights=request.usage_rights,
            custom_terms=request.custom_terms,
        )  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error("Error creating model license: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/verification/verify")
@rate_limit(rate=20, per=60)
async def verify_model(
    request: Request,
    verification_request: ModelVerificationRequest,
    offer_id: str,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Verify model quality and performance"""
    try:
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        result = await enhanced_service.verify_model(offer_id=offer_id, verification_type=request.verification_type)  # type: ignore[attr-defined]
        return result
    except Exception as e:
        logger.error("Error verifying model: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/analytics")
@rate_limit(rate=200, per=60)
async def get_marketplace_analytics(
    request: Request,
    analytics_request: MarketplaceAnalyticsRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> dict[str, Any]:  # type: ignore[arg-type]
    """Get marketplace analytics and insights"""
    try:
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        analytics = await enhanced_service.get_marketplace_analytics(period_days=request.period_days, metrics=request.metrics)  # type: ignore[attr-defined]
        return analytics
    except Exception as e:
        logger.error("Error getting marketplace analytics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
