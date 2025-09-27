from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JobState(str, Enum):
    queued = "QUEUED"
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"
    canceled = "CANCELED"
    expired = "EXPIRED"


class Constraints(BaseModel):
    gpu: Optional[str] = None
    cuda: Optional[str] = None
    min_vram_gb: Optional[int] = None
    models: Optional[list[str]] = None
    region: Optional[str] = None
    max_price: Optional[float] = None


class JobCreate(BaseModel):
    payload: Dict[str, Any]
    constraints: Constraints = Field(default_factory=Constraints)
    ttl_seconds: int = 900


class JobView(BaseModel):
    job_id: str
    state: JobState
    assigned_miner_id: Optional[str] = None
    requested_at: datetime
    expires_at: datetime
    error: Optional[str] = None


class JobResult(BaseModel):
    result: Optional[Dict[str, Any]] = None
    receipt: Optional[Dict[str, Any]] = None


class MinerRegister(BaseModel):
    capabilities: Dict[str, Any]
    concurrency: int = 1
    region: Optional[str] = None


class MinerHeartbeat(BaseModel):
    inflight: int = 0
    status: str = "ONLINE"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PollRequest(BaseModel):
    max_wait_seconds: int = 15


class AssignedJob(BaseModel):
    job_id: str
    payload: Dict[str, Any]
    constraints: Constraints


class JobResultSubmit(BaseModel):
    result: Dict[str, Any]
    metrics: Dict[str, Any] = Field(default_factory=dict)


class JobFailSubmit(BaseModel):
    error_code: str
    error_message: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
