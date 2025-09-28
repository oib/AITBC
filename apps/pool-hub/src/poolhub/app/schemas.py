from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MatchRequestPayload(BaseModel):
    job_id: str
    requirements: Dict[str, Any] = Field(default_factory=dict)
    hints: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=1, ge=1, le=50)


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
