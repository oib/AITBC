"""Edge metrics-related schemas for Edge API Service"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


class EdgeMetrics(SQLModel, table=True):
    """Edge performance metrics"""
    
    __tablename__ = "edge_metrics"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"edge_metric_{uuid4().hex[:8]}", primary_key=True)
    island_id: str = Field(index=True)
    gpu_id: str | None = Field(default=None, index=True)
    database_id: str | None = Field(default=None, index=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # GPU metrics
    gpu_utilization: float = Field(default=0.0)
    gpu_temperature: float | None = Field(default=None)
    gpu_power: float | None = Field(default=None)
    
    # Memory metrics
    memory_utilization: float = Field(default=0.0)
    memory_used_gb: float = Field(default=0.0)
    
    # Request metrics
    request_rate: float = Field(default=0.0)  # requests per second
    latency_avg: float = Field(default=0.0)  # milliseconds
    active_requests: int = Field(default=0)
    
    # Database metrics
    database_size_gb: float = Field(default=0.0)
    query_rate: float = Field(default=0.0)  # queries per second
    sync_lag: float = Field(default=0.0)  # seconds behind
