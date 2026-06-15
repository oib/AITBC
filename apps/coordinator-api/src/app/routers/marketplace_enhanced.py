from typing import Annotated

from sqlalchemy.orm import Session

"\nEnhanced Marketplace API Router - Phase 6.5\nREST API endpoints for advanced marketplace features including royalties, licensing, and analytics\n"
from aitbc import get_logger  # noqa: E402
from aitbc.rate_limiting import rate_limit  # noqa: E402

logger = get_logger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from ..contexts.marketplace.services.marketplace_enhanced import EnhancedMarketplaceService  # noqa: E402
from ..deps import require_admin_key  # noqa: E402
from ..domain import MarketplaceOffer  # type: ignore[attr-defined]  # noqa: E402
from ..schemas.marketplace_enhanced import (  # noqa: E402
    MarketplaceAnalyticsResponse,
    ModelLicenseRequest,
    ModelLicenseResponse,
    ModelVerificationRequest,
    ModelVerificationResponse,
    RoyaltyDistributionRequest,
    RoyaltyDistributionResponse,
)
from ..storage import get_session  # noqa: E402

router = APIRouter(prefix="/marketplace/enhanced", tags=["Enhanced Marketplace"])


@router.post("/royalties/distribution", response_model=RoyaltyDistributionResponse)
@rate_limit(rate=20, per=60)
async def create_royalty_distribution(
    request: Request,
    offer_id: str,
    royalty_tiers: RoyaltyDistributionRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> RoyaltyDistributionResponse:  # type: ignore[arg-type]
    """Create sophisticated royalty distribution for marketplace offer"""
    try:
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        result = await enhanced_service.create_royalty_distribution(
            offer_id=offer_id, royalty_tiers=royalty_tiers.tiers, dynamic_rates=royalty_tiers.dynamic_rates
        )
        return RoyaltyDistributionResponse(
            offer_id=result["offer_id"],
            royalty_tiers=result["tiers"],
            dynamic_rates=result["dynamic_rates"],
            created_at=result["created_at"],
        )
    except Exception as e:
        logger.error("Error creating royalty distribution: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/royalties/calculate", response_model=dict)
@rate_limit(rate=50, per=60)
async def calculate_royalties(
    request: Request,
    offer_id: str,
    sale_amount: float,
    transaction_id: str | None = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> dict:  # type: ignore[arg-type]
    """Calculate and distribute royalties for a sale"""
    try:
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        royalties = await enhanced_service.calculate_royalties(
            offer_id=offer_id, sale_amount=sale_amount, transaction_id=transaction_id
        )
        return royalties
    except Exception as e:
        logger.error("Error calculating royalties: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/licenses/create", response_model=ModelLicenseResponse)
@rate_limit(rate=20, per=60)
async def create_model_license(
    request: Request,
    offer_id: str,
    license_request: ModelLicenseRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> ModelLicenseResponse:  # type: ignore[arg-type]
    """Create model license and IP protection"""
    try:
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        result = await enhanced_service.create_model_license(
            offer_id=offer_id,
            license_type=license_request.license_type,
            terms=license_request.terms,
            usage_rights=license_request.usage_rights,
            custom_terms=license_request.custom_terms,
        )  # type: ignore[arg-type]
        return ModelLicenseResponse(
            offer_id=result["offer_id"],
            license_type=result["license_type"],
            terms=result["terms"],
            usage_rights=result["usage_rights"],
            custom_terms=result["custom_terms"],
            created_at=result["created_at"],
        )
    except Exception as e:
        logger.error("Error creating model license: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/verification/verify", response_model=ModelVerificationResponse)
@rate_limit(rate=20, per=60)
async def verify_model(
    request: Request,
    offer_id: str,
    verification_request: ModelVerificationRequest,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> ModelVerificationResponse:  # type: ignore[arg-type]
    """Perform advanced model verification"""
    try:
        offer = session.get(MarketplaceOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if offer.provider != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        result = await enhanced_service.verify_model(
            offer_id=offer_id, verification_type=verification_request.verification_type
        )
        return ModelVerificationResponse(
            offer_id=result["offer_id"],
            verification_type=result["verification_type"],
            status=result["status"],
            checks=result["checks"],
            created_at=result["created_at"],
        )
    except Exception as e:
        logger.error("Error verifying model: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/analytics", response_model=MarketplaceAnalyticsResponse)
@rate_limit(rate=200, per=60)
async def get_marketplace_analytics(
    request: Request,
    period_days: int = 30,
    metrics: list[str] | None = None,
    session: Session = Depends(Annotated[Session, Depends(get_session)]),
    current_user: str = Depends(require_admin_key()),
) -> MarketplaceAnalyticsResponse:  # type: ignore[arg-type]
    """Get comprehensive marketplace analytics"""
    try:
        enhanced_service = EnhancedMarketplaceService(session)  # type: ignore[arg-type]
        analytics = await enhanced_service.get_marketplace_analytics(period_days=period_days, metrics=metrics)  # type: ignore[arg-type]
        return MarketplaceAnalyticsResponse(
            period_days=analytics["period_days"],
            start_date=analytics["start_date"],
            end_date=analytics["end_date"],
            metrics=analytics["metrics"],
        )
    except Exception as e:
        logger.error("Error getting marketplace analytics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
