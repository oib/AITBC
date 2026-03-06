"""
Enhanced Marketplace Service Tests - Phase 6.5
Tests for sophisticated royalty distribution, model licensing, and advanced verification
"""

import pytest
import asyncio
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, create_engine
from sqlalchemy import StaticPool

from src.app.services.marketplace_enhanced import (
    EnhancedMarketplaceService, RoyaltyTier, LicenseType, VerificationStatus
)
from src.app.domain import MarketplaceOffer, MarketplaceBid
from src.app.schemas.marketplace_enhanced import (
    RoyaltyDistributionRequest, ModelLicenseRequest, ModelVerificationRequest
)


@pytest.fixture
def session():
    """Create test database session"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    # Create tables
    MarketplaceOffer.metadata.create_all(engine)
    MarketplaceBid.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


@pytest.fixture
def sample_offer(session: Session):
    """Create sample marketplace offer"""
    offer = MarketplaceOffer(
        id=f"offer_{uuid4().hex[:8]}",
        provider="test_provider",
        capacity=100,
        price=0.1,
        sla="standard",
        status="open",
        attributes={}
    )
    session.add(offer)
    session.commit()
    return offer


class TestEnhancedMarketplaceService:
    """Test enhanced marketplace service functionality"""
    
    @pytest.mark.asyncio
    async def test_create_royalty_distribution(self, session: Session, sample_offer: MarketplaceOffer):
        """Test creating sophisticated royalty distribution"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        royalty_tiers = {
            "primary": 10.0,
            "secondary": 5.0,
            "tertiary": 2.0
        }
        
        result = await enhanced_service.create_royalty_distribution(
            offer_id=sample_offer.id,
            royalty_tiers=royalty_tiers,
            dynamic_rates=True
        )
        
        assert result["offer_id"] == sample_offer.id
        assert result["tiers"] == royalty_tiers
        assert result["dynamic_rates"] is True
        assert "created_at" in result
        
        # Verify stored in offer attributes
        updated_offer = session.get(MarketplaceOffer, sample_offer.id)
        assert "royalty_distribution" in updated_offer.attributes
        assert updated_offer.attributes["royalty_distribution"]["tiers"] == royalty_tiers
    
    @pytest.mark.asyncio
    async def test_create_royalty_distribution_invalid_percentage(self, session: Session, sample_offer: MarketplaceOffer):
        """Test royalty distribution with invalid percentage"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        # Invalid: total percentage exceeds 100%
        royalty_tiers = {
            "primary": 60.0,
            "secondary": 50.0,  # Total: 110%
        }
        
        with pytest.raises(ValueError, match="Total royalty percentage cannot exceed 100%"):
            await enhanced_service.create_royalty_distribution(
                offer_id=sample_offer.id,
                royalty_tiers=royalty_tiers
            )
    
    @pytest.mark.asyncio
    async def test_calculate_royalties(self, session: Session, sample_offer: MarketplaceOffer):
        """Test calculating royalties for a sale"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        # First create royalty distribution
        royalty_tiers = {"primary": 10.0, "secondary": 5.0}
        await enhanced_service.create_royalty_distribution(
            offer_id=sample_offer.id,
            royalty_tiers=royalty_tiers
        )
        
        # Calculate royalties
        sale_amount = 1000.0
        royalties = await enhanced_service.calculate_royalties(
            offer_id=sample_offer.id,
            sale_amount=sale_amount
        )
        
        assert royalties["primary"] == 100.0  # 10% of 1000
        assert royalties["secondary"] == 50.0  # 5% of 1000
    
    @pytest.mark.asyncio
    async def test_calculate_royalties_default(self, session: Session, sample_offer: MarketplaceOffer):
        """Test calculating royalties with default distribution"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        # Calculate royalties without existing distribution
        sale_amount = 1000.0
        royalties = await enhanced_service.calculate_royalties(
            offer_id=sample_offer.id,
            sale_amount=sale_amount
        )
        
        # Should use default 10% primary royalty
        assert royalties["primary"] == 100.0  # 10% of 1000
    
    @pytest.mark.asyncio
    async def test_create_model_license(self, session: Session, sample_offer: MarketplaceOffer):
        """Test creating model license and IP protection"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        license_request = {
            "license_type": LicenseType.COMMERCIAL,
            "terms": {"duration": "perpetual", "territory": "worldwide"},
            "usage_rights": ["commercial_use", "modification", "distribution"],
            "custom_terms": {"attribution": "required"}
        }
        
        result = await enhanced_service.create_model_license(
            offer_id=sample_offer.id,
            license_type=license_request["license_type"],
            terms=license_request["terms"],
            usage_rights=license_request["usage_rights"],
            custom_terms=license_request["custom_terms"]
        )
        
        assert result["offer_id"] == sample_offer.id
        assert result["license_type"] == LicenseType.COMMERCIAL.value
        assert result["terms"] == license_request["terms"]
        assert result["usage_rights"] == license_request["usage_rights"]
        assert result["custom_terms"] == license_request["custom_terms"]
        
        # Verify stored in offer attributes
        updated_offer = session.get(MarketplaceOffer, sample_offer.id)
        assert "license" in updated_offer.attributes
    
    @pytest.mark.asyncio
    async def test_verify_model_comprehensive(self, session: Session, sample_offer: MarketplaceOffer):
        """Test comprehensive model verification"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        result = await enhanced_service.verify_model(
            offer_id=sample_offer.id,
            verification_type="comprehensive"
        )
        
        assert result["offer_id"] == sample_offer.id
        assert result["verification_type"] == "comprehensive"
        assert result["status"] in [VerificationStatus.VERIFIED.value, VerificationStatus.FAILED.value]
        assert "checks" in result
        assert "quality" in result["checks"]
        assert "performance" in result["checks"]
        assert "security" in result["checks"]
        assert "compliance" in result["checks"]
        
        # Verify stored in offer attributes
        updated_offer = session.get(MarketplaceOffer, sample_offer.id)
        assert "verification" in updated_offer.attributes
    
    @pytest.mark.asyncio
    async def test_verify_model_performance(self, session: Session, sample_offer: MarketplaceOffer):
        """Test performance-only model verification"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        result = await enhanced_service.verify_model(
            offer_id=sample_offer.id,
            verification_type="performance"
        )
        
        assert result["verification_type"] == "performance"
        assert "performance" in result["checks"]
        assert len(result["checks"]) == 1  # Only performance check
    
    @pytest.mark.asyncio
    async def test_get_marketplace_analytics(self, session: Session, sample_offer: MarketplaceOffer):
        """Test getting comprehensive marketplace analytics"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        analytics = await enhanced_service.get_marketplace_analytics(
            period_days=30,
            metrics=["volume", "trends", "performance", "revenue"]
        )
        
        assert analytics["period_days"] == 30
        assert "start_date" in analytics
        assert "end_date" in analytics
        assert "metrics" in analytics
        
        # Check all requested metrics are present
        metrics = analytics["metrics"]
        assert "volume" in metrics
        assert "trends" in metrics
        assert "performance" in metrics
        assert "revenue" in metrics
        
        # Check volume metrics structure
        volume = metrics["volume"]
        assert "total_offers" in volume
        assert "total_capacity" in volume
        assert "average_capacity" in volume
        assert "daily_average" in volume
    
    @pytest.mark.asyncio
    async def test_get_marketplace_analytics_default_metrics(self, session: Session, sample_offer: MarketplaceOffer):
        """Test marketplace analytics with default metrics"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        analytics = await enhanced_service.get_marketplace_analytics(period_days=30)
        
        # Should include default metrics
        metrics = analytics["metrics"]
        assert "volume" in metrics
        assert "trends" in metrics
        assert "performance" in metrics
        assert "revenue" in metrics
    
    @pytest.mark.asyncio
    async def test_nonexistent_offer_royalty_distribution(self, session: Session):
        """Test royalty distribution for nonexistent offer"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        with pytest.raises(ValueError, match="Offer not found"):
            await enhanced_service.create_royalty_distribution(
                offer_id="nonexistent",
                royalty_tiers={"primary": 10.0}
            )
    
    @pytest.mark.asyncio
    async def test_nonexistent_offer_license_creation(self, session: Session):
        """Test license creation for nonexistent offer"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        with pytest.raises(ValueError, match="Offer not found"):
            await enhanced_service.create_model_license(
                offer_id="nonexistent",
                license_type=LicenseType.COMMERCIAL,
                terms={},
                usage_rights=[]
            )
    
    @pytest.mark.asyncio
    async def test_nonexistent_offer_verification(self, session: Session):
        """Test model verification for nonexistent offer"""
        
        enhanced_service = EnhancedMarketplaceService(session)
        
        with pytest.raises(ValueError, match="Offer not found"):
            await enhanced_service.verify_model(
                offer_id="nonexistent",
                verification_type="comprehensive"
            )
