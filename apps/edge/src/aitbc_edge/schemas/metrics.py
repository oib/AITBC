"""Edge metrics-related schemas for Edge API Service"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class EdgeMetrics(SQLModel, table=True):
    """Edge performance metrics"""

    __tablename__ = "edge_metrics"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"edge_metric_{uuid4().hex[:8]}", primary_key=True)
    metric_id: str = Field(index=True)
    gpu_id: str = Field(index=True)
    metrics_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    extra_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))
