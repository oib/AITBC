"""
Shared types and enums for the AITBC Coordinator API
"""

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
