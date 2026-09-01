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
    # G3: how long this job's customer may review the result before the escrow
    # releases. None takes the operator's default; the coordinator clamps it.
    acceptance_window_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Seconds to review the result before payment auto-releases (0 releases immediately)",
    )
    bond_required: bool = Field(default=False, description="Require a performance bond for this job")
    min_bond_amount: Decimal | None = Field(default=None, description="Minimum bond amount required for provider eligibility")
    confidential: bool = Field(default=False, description="Mark this job as confidential")
    required_enclave_measurement: str | None = Field(
        default=None, description="Required TEE enclave measurement for confidential jobs"
    )
    # G3: deterministic decoding makes a job reproducible so the coordinator can
    # re-run it in shadow mode and compare results exactly.
    deterministic_decoding: bool = Field(default=False, description="Use deterministic decoding for reproducible verification")
    decode_seed: int | None = Field(
        default=None, description="Optional seed for deterministic decoding (auto-assigned if unset)"
    )
