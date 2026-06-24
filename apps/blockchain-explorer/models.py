"""Pydantic models for the Blockchain Explorer API."""

from pydantic import BaseModel, Field


class TransactionSearch(BaseModel):
    address: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    tx_type: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class BlockSearch(BaseModel):
    validator: str | None = None
    since: str | None = None
    until: str | None = None
    min_tx: int | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AnalyticsRequest(BaseModel):
    period: str = Field(default="24h", pattern="^(1h|24h|7d|30d)$")
    granularity: str | None = None
    metrics: list[str] = Field(default_factory=list)
