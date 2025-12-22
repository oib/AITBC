from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class MatchRequestPayload(BaseModel):
    job_id: str
    requirements: Dict[str, Any] = Field(default_factory=dict)
    hints: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=1, ge=1, le=50)
    redis_error: Optional[str] = None


class MatchCandidate(BaseModel):
    miner_id: str
    addr: str
    proto: str
    score: float
    explain: Optional[str] = None
    eta_ms: Optional[int] = None
    price: Optional[float] = None


class MatchResponse(BaseModel):
    job_id: str
    candidates: List[MatchCandidate]


class HealthResponse(BaseModel):
    status: str
    db: bool
    redis: bool
    miners_online: int
    db_error: Optional[str] = None
    redis_error: Optional[str] = None


class MetricsResponse(BaseModel):
    detail: str = "Prometheus metrics output"


# Service Configuration Schemas
class ServiceConfigBase(BaseModel):
    """Base service configuration"""
    enabled: bool = Field(False, description="Whether service is enabled")
    config: Dict[str, Any] = Field(default_factory=dict, description="Service-specific configuration")
    pricing: Dict[str, Any] = Field(default_factory=dict, description="Pricing configuration")
    capabilities: List[str] = Field(default_factory=list, description="Service capabilities")
    max_concurrent: int = Field(1, ge=1, le=10, description="Maximum concurrent jobs")


class ServiceConfigCreate(ServiceConfigBase):
    """Service configuration creation request"""
    pass


class ServiceConfigUpdate(BaseModel):
    """Service configuration update request"""
    enabled: Optional[bool] = Field(None, description="Whether service is enabled")
    config: Optional[Dict[str, Any]] = Field(None, description="Service-specific configuration")
    pricing: Optional[Dict[str, Any]] = Field(None, description="Pricing configuration")
    capabilities: Optional[List[str]] = Field(None, description="Service capabilities")
    max_concurrent: Optional[int] = Field(None, ge=1, le=10, description="Maximum concurrent jobs")


class ServiceConfigResponse(ServiceConfigBase):
    """Service configuration response"""
    service_type: str = Field(..., description="Service type")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")
    
    class Config:
        from_attributes = True
