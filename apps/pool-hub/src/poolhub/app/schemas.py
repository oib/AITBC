from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MatchRequestPayload(BaseModel):
    job_id: str
    requirements: dict[str, Any] = Field(default_factory=dict)
    hints: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=1, ge=1, le=50)
    redis_error: str | None = None


class MatchCandidate(BaseModel):
    """A miner offered for a job.

    ``price`` is ``Decimal``, not ``float``: it is read from ``Miner.base_price``
    (``Numeric(20, 8)``) in ``routers/match.py`` and written back to ``MatchResult.price``
    (``Numeric(20, 8)``) in ``repositories/match_repository.py``. Declaring it ``float``
    put a binary floating-point round trip in the middle of that path, losing precision at
    the eighth decimal for no reason. ``score`` stays ``float`` — it is a ranking weight,
    not money.
    """

    miner_id: str
    addr: str
    proto: str
    score: float
    explain: str | None = None
    eta_ms: int | None = None
    price: Decimal | None = None


class MatchResponse(BaseModel):
    job_id: str
    candidates: list[MatchCandidate]


class HealthResponse(BaseModel):
    status: str
    db: bool
    redis: bool
    # None when the count could not be read (V23-96).  Reporting 0 there would be
    # indistinguishable from "no miners are online", which is a different answer.
    miners_online: int | None = None
    db_error: str | None = None
    redis_error: str | None = None
    miners_error: str | None = None


class MetricsResponse(BaseModel):
    detail: str = "Prometheus metrics output"


# Service Configuration Schemas
class ServiceConfigBase(BaseModel):
    """Base service configuration"""

    enabled: bool = Field(False, description="Whether service is enabled")
    config: dict[str, Any] = Field(default_factory=dict, description="Service-specific configuration")
    pricing: dict[str, Any] = Field(default_factory=dict, description="Pricing configuration")
    capabilities: list[str] = Field(default_factory=list, description="Service capabilities")
    max_concurrent: int = Field(1, ge=1, le=10, description="Maximum concurrent jobs")


class ServiceConfigCreate(ServiceConfigBase):
    """Service configuration creation request"""

    pass


class ServiceConfigUpdate(BaseModel):
    """Service configuration update request"""

    enabled: bool | None = Field(None, description="Whether service is enabled")
    config: dict[str, Any] | None = Field(None, description="Service-specific configuration")
    pricing: dict[str, Any] | None = Field(None, description="Pricing configuration")
    capabilities: list[str] | None = Field(None, description="Service capabilities")
    max_concurrent: int | None = Field(None, ge=1, le=10, description="Maximum concurrent jobs")


class ServiceConfigResponse(ServiceConfigBase):
    """Service configuration response"""

    service_type: str = Field(..., description="Service type")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")

    model_config = ConfigDict(from_attributes=True)
