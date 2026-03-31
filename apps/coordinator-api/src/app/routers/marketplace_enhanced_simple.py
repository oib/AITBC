
from sqlalchemy.orm import Session

"""
Enhanced Marketplace API Router - Simplified Version
REST API endpoints for enhanced marketplace features
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..deps import require_admin_key
from ..services.marketplace_enhanced_simple import EnhancedMarketplaceService, LicenseType, VerificationType
from ..storage import get_session

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
async def create_royalty_distribution(
    request: RoyaltyDistributionRequest,
    offer_id: str,
    session: Session = Depends(get_session),
    current_user: str = Depends(require_admin_key()),
):
    """Create royalty distribution for marketplace offer"""

    try:
        enhanced_service = EnhancedMarketplaceService(session)
        result = await enhanced_service.create_royalty_distribution(
            offer_id=offer_id, royalty_tiers=request.tiers, dynamic_rates=request.dynamic_rates
        )

        return result

    except Exception as e:
        logger.error(f"Error creating royalty distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/royalty/calculate/{offer_id}")
async def calculate_royalties(
    offer_id: str,
    sale_amount: float,
    session: Session = Depends(get_session),
    current_user: str = Depends(require_admin_key()),
):
    """Calculate royalties for a sale"""

    try:
        enhanced_service = EnhancedMarketplaceService(session)
        royalties = await enhanced_service.calculate_royalties(offer_id=offer_id, sale_amount=sale_amount)

        return royalties

    except Exception as e:
        logger.error(f"Error calculating royalties: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/license/create")
async def create_model_license(
    request: ModelLicenseRequest,
    offer_id: str,
    session: Session = Depends(get_session),
    current_user: str = Depends(require_admin_key()),
):
    """Create model license for marketplace offer"""

    try:
        enhanced_service = EnhancedMarketplaceService(session)
        result = await enhanced_service.create_model_license(
            offer_id=offer_id,
            license_type=request.license_type,
            terms=request.terms,
            usage_rights=request.usage_rights,
            custom_terms=request.custom_terms,
        )

        return result

    except Exception as e:
        logger.error(f"Error creating model license: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verification/verify")
async def verify_model(
    request: ModelVerificationRequest,
    offer_id: str,
    session: Session = Depends(get_session),
    current_user: str = Depends(require_admin_key()),
):
    """Verify model quality and performance"""

    try:
        enhanced_service = EnhancedMarketplaceService(session)
        result = await enhanced_service.verify_model(offer_id=offer_id, verification_type=request.verification_type)

        return result

    except Exception as e:
        logger.error(f"Error verifying model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics")
async def get_marketplace_analytics(
    request: MarketplaceAnalyticsRequest,
    session: Session = Depends(get_session),
    current_user: str = Depends(require_admin_key()),
):
    """Get marketplace analytics and insights"""

    try:
        enhanced_service = EnhancedMarketplaceService(session)
        analytics = await enhanced_service.get_marketplace_analytics(period_days=request.period_days, metrics=request.metrics)

        return analytics

    except Exception as e:
        logger.error(f"Error getting marketplace analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
