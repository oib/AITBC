"""
Enhanced Marketplace Pydantic Schemas - Phase 6.5
Request and response models for advanced marketplace features
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class RoyaltyTier(str, Enum):
    """Royalty distribution tiers"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


class LicenseType(str, Enum):
    """Model license types"""
    COMMERCIAL = "commercial"
    RESEARCH = "research"
    EDUCATIONAL = "educational"
    CUSTOM = "custom"


class VerificationType(str, Enum):
    """Model verification types"""
    COMPREHENSIVE = "comprehensive"
    PERFORMANCE = "performance"
    SECURITY = "security"


# Request Models
class RoyaltyDistributionRequest(BaseModel):
    """Request for creating royalty distribution"""
    tiers: Dict[str, float] = Field(..., description="Royalty tiers and percentages")
    dynamic_rates: bool = Field(default=False, description="Enable dynamic royalty rates")


class ModelLicenseRequest(BaseModel):
    """Request for creating model license"""
    license_type: LicenseType = Field(..., description="Type of license")
    terms: Dict[str, Any] = Field(..., description="License terms and conditions")
    usage_rights: List[str] = Field(..., description="List of usage rights")
    custom_terms: Optional[Dict[str, Any]] = Field(default=None, description="Custom license terms")


class ModelVerificationRequest(BaseModel):
    """Request for model verification"""
    verification_type: VerificationType = Field(default=VerificationType.COMPREHENSIVE, description="Type of verification")


class MarketplaceAnalyticsRequest(BaseModel):
    """Request for marketplace analytics"""
    period_days: int = Field(default=30, description="Period in days for analytics")
    metrics: Optional[List[str]] = Field(default=None, description="Specific metrics to retrieve")


# Response Models
class RoyaltyDistributionResponse(BaseModel):
    """Response for royalty distribution creation"""
    offer_id: str = Field(..., description="Offer ID")
    royalty_tiers: Dict[str, float] = Field(..., description="Royalty tiers and percentages")
    dynamic_rates: bool = Field(..., description="Dynamic rates enabled")
    created_at: datetime = Field(..., description="Creation timestamp")


class ModelLicenseResponse(BaseModel):
    """Response for model license creation"""
    offer_id: str = Field(..., description="Offer ID")
    license_type: str = Field(..., description="License type")
    terms: Dict[str, Any] = Field(..., description="License terms")
    usage_rights: List[str] = Field(..., description="Usage rights")
    custom_terms: Optional[Dict[str, Any]] = Field(default=None, description="Custom terms")
    created_at: datetime = Field(..., description="Creation timestamp")


class ModelVerificationResponse(BaseModel):
    """Response for model verification"""
    offer_id: str = Field(..., description="Offer ID")
    verification_type: str = Field(..., description="Verification type")
    status: str = Field(..., description="Verification status")
    checks: Dict[str, Any] = Field(..., description="Verification check results")
    created_at: datetime = Field(..., description="Verification timestamp")


class MarketplaceAnalyticsResponse(BaseModel):
    """Response for marketplace analytics"""
    period_days: int = Field(..., description="Period in days")
    start_date: str = Field(..., description="Start date ISO string")
    end_date: str = Field(..., description="End date ISO string")
    metrics: Dict[str, Any] = Field(..., description="Analytics metrics")
