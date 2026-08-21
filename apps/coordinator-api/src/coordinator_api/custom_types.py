"""
Shared types and enums for the AITBC Coordinator API
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class JobState(StrEnum):
    queued = "QUEUED"
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"
    canceled = "CANCELED"
    expired = "EXPIRED"


class Constraints(BaseModel):
    gpu: str | None = None
    cuda: str | None = None
    min_vram_gb: int | None = None
    models: list[str] | None = None
    region: str | None = None
    max_price: Decimal | None = None
    zk_proof_required: bool = Field(default=False, description="Require a ZK receipt proof for this job")
    tee_attestation_required: bool = Field(default=False, description="Require a TEE attestation for this job")
    tee_enclave_id: str | None = Field(default=None, description="Required enclave identity for TEE attestation")
    min_reputation: float | None = None
