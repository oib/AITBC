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
    auto_reinvest_pct: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
        description="Percentage of released payment to auto-stake as reinvestment",
    )
    bond_required: bool = Field(default=False, description="Require a performance bond for this job")
    min_bond_amount: Decimal | None = Field(default=None, description="Minimum bond amount required for provider eligibility")
    confidential: bool = Field(default=False, description="Mark this job as confidential")
    required_enclave_measurement: str | None = Field(
        default=None, description="Required TEE enclave measurement for confidential jobs"
    )
