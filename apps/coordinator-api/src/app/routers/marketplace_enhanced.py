from sqlalchemy.orm import Session
from typing import Annotated
"""
Enhanced Marketplace API Router - Phase 6.5
REST API endpoints for advanced marketplace features including royalties, licensing, and analytics
"""

from typing import List, Optional
from aitbc.logging import get_logger

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..domain import MarketplaceOffer
from ..services.marketplace_enhanced import EnhancedMarketplaceService, RoyaltyTier, LicenseType
from ..storage import Annotated[Session, Depends(get_session)], get_session
from ..deps import require_admin_key
from ..schemas.marketplace_enhanced import (
    RoyaltyDistributionRequest, RoyaltyDistributionResponse,
    ModelLicenseRequest, ModelLicenseResponse,
    ModelVerificationRequest, ModelVerificationResponse,
    MarketplaceAnalyticsRequest, MarketplaceAnalyticsResponse
)

logger = get_logger(__name__)

router = APIRouter(prefix="/marketplace/enhanced", tags=["Enhanced Marketplace"])


@router.post("/royalties/distribution", response_model=RoyaltyDistributionResponse)
async def create_royalty_distribution(
    offer_id: str,
    royalty_tiers: RoyaltyDistributionRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Create sophisticated royalty distribution for marketplace offer"""
    
    try:
        # Verify offer exists and user has access
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        enhanced_service = EnhancedMarketplaceService(session)
        result = await enhanced_service.create_royalty_distribution(
            offer_id=offer_id,
            royalty_tiers=royalty_tiers.tiers,
            dynamic_rates=royalty_tiers.dynamic_rates
        )
        
        return RoyaltyDistributionResponse(
            offer_id=result["offer_id"],
            royalty_tiers=result["tiers"],
            dynamic_rates=result["dynamic_rates"],
            created_at=result["created_at"]
        )
        
    except Exception as e:
        logger.error(f"Error creating royalty distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/royalties/calculate", response_model=dict)
async def calculate_royalties(
    offer_id: str,
    sale_amount: float,
    transaction_id: Optional[str] = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Calculate and distribute royalties for a sale"""
    
    try:
        # Verify offer exists and user has access
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        enhanced_service = EnhancedMarketplaceService(session)
        royalties = await enhanced_service.calculate_royalties(
            offer_id=offer_id,
            sale_amount=sale_amount,
            transaction_id=transaction_id
        )
        
        return royalties
        
    except Exception as e:
        logger.error(f"Error calculating royalties: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/licenses/create", response_model=ModelLicenseResponse)
async def create_model_license(
    offer_id: str,
    license_request: ModelLicenseRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Create model license and IP protection"""
    
    try:
        # Verify offer exists and user has access
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        enhanced_service = EnhancedMarketplaceService(session)
        result = await enhanced_service.create_model_license(
            offer_id=offer_id,
            license_type=license_request.license_type,
            terms=license_request.terms,
            usage_rights=license_request.usage_rights,
            custom_terms=license_request.custom_terms
        )
        
        return ModelLicenseResponse(
            offer_id=result["offer_id"],
            license_type=result["license_type"],
            terms=result["terms"],
            usage_rights=result["usage_rights"],
            custom_terms=result["custom_terms"],
            created_at=result["created_at"]
        )
        
    except Exception as e:
        logger.error(f"Error creating model license: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verification/verify", response_model=ModelVerificationResponse)
async def verify_model(
    offer_id: str,
    verification_request: ModelVerificationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Perform advanced model verification"""
    
    try:
        # Verify offer exists and user has access
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        enhanced_service = EnhancedMarketplaceService(session)
        result = await enhanced_service.verify_model(
            offer_id=offer_id,
            verification_type=verification_request.verification_type
        )
        
        return ModelVerificationResponse(
            offer_id=result["offer_id"],
            verification_type=result["verification_type"],
            status=result["status"],
            checks=result["checks"],
            created_at=result["created_at"]
        )
        
    except Exception as e:
        logger.error(f"Error verifying model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics", response_model=MarketplaceAnalyticsResponse)
async def get_marketplace_analytics(
    period_days: int = 30,
    metrics: Optional[List[str]] = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key())
):
    """Get comprehensive marketplace analytics"""
    
    try:
        enhanced_service = EnhancedMarketplaceService(session)
        analytics = await enhanced_service.get_marketplace_analytics(
            period_days=period_days,
            metrics=metrics
        )
        
        return MarketplaceAnalyticsResponse(
            period_days=analytics["period_days"],
            start_date=analytics["start_date"],
            end_date=analytics["end_date"],
            metrics=analytics["metrics"]
        )
        
    except Exception as e:
        logger.error(f"Error getting marketplace analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
