"""
Shared types and enums for the AITBC Coordinator API
"""

from decimal import Decimal

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Constraint keys the coordinator honored via TEE attestation before #2375
# removed the enclave machinery. Accepting them silently would be a fail-open
# privacy claim — the prompt and result travel to the provider like any other
# job — so job creation rejects them outright (see Constraints below).
RETIRED_CONSTRAINT_KEYS = frozenset({"tee_attestation_required", "tee_enclave_id", "required_enclave_measurement"})
CONFIDENTIAL_UNSUPPORTED_MSG = "confidential/TEE jobs are not supported: TEE attestation was removed in #2375"


class JobState(StrEnum):
    queued = "QUEUED"
    running = "RUNNING"
    completed = "COMPLETED"
    failed = "FAILED"
    canceled = "CANCELED"
    expired = "EXPIRED"


# Aliases accepted for the ?status= filter on the job-list endpoints. "pending"
# is the name the CLI and scenario docs use for a not-yet-started job; it maps to
# QUEUED. "all"/"any" mean "no filter" and resolve to None.
JOB_STATE_ALIASES: dict[str, JobState] = {"PENDING": JobState.queued}
JOB_STATE_UNFILTERED = {"ALL", "ANY", "*"}


def parse_job_state_filter(value: str) -> JobState | None:
    """Resolve a ``?status=`` query value to a JobState.

    Returns ``None`` for the explicit "no filter" values (all/any/*). Raises
    ``ValueError`` for anything that is neither a JobState name/value nor a
    known alias, so callers can answer 400 instead of silently dropping the
    filter.
    """
    normalized = value.strip().upper()
    if normalized in JOB_STATE_UNFILTERED:
        return None
    if normalized in JOB_STATE_ALIASES:
        return JOB_STATE_ALIASES[normalized]
    return JobState(normalized)


def job_state_filter_help() -> str:
    """Human-readable list of valid status filter values for error messages."""
    valid = ", ".join(s.value.lower() for s in JobState)
    aliases = ", ".join(f"{k.lower()}→{v.value.lower()}" for k, v in JOB_STATE_ALIASES.items())
    return f"valid values: {valid}; aliases: {aliases}; 'all' disables the filter"


class Constraints(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _reject_retired_constraints(cls, data: Any) -> Any:
        """Fail closed on confidential/TEE claims (#2474).

        ``extra="ignore"`` would otherwise drop the removed ``tee_*`` keys and
        ``confidential: true`` has no consumer, so a privacy request would be
        accepted and dispatched as an ordinary job. Reject at validation so
        the API answers 422. Already-built instances pass through, and
        ``from_record`` sanitizes legacy stored rows.
        """
        if isinstance(data, Constraints) or not isinstance(data, dict):
            return data
        if RETIRED_CONSTRAINT_KEYS & data.keys() or data.get("confidential"):
            raise ValueError(CONFIDENTIAL_UNSUPPORTED_MSG)
        return data

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> "Constraints":
        """Rehydrate constraints stored on a job row.

        Rows written before #2375 may carry confidential/TEE keys that
        creation now rejects; strip them so reads and dispatch of legacy jobs
        keep working.
        """
        cleaned = {k: v for k, v in raw.items() if k not in RETIRED_CONSTRAINT_KEYS}
        if cleaned.get("confidential"):
            cleaned["confidential"] = False
        return cls(**cleaned)

    gpu: str | None = None
    cuda: str | None = None
    min_vram_gb: int | None = None
    models: list[str] | None = None
    region: str | None = None
    max_price: Decimal | None = None
    zk_proof_required: bool = Field(default=False, description="Require a ZK receipt proof for this job")
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
    # G3: deterministic decoding makes a job reproducible so the coordinator can
    # re-run it in shadow mode and compare results exactly.
    deterministic_decoding: bool = Field(default=False, description="Use deterministic decoding for reproducible verification")
    decode_seed: int | None = Field(
        default=None, description="Optional seed for deterministic decoding (auto-assigned if unset)"
    )
    # Server-only spot-check fields are intentionally NOT declared here. They are
    # set only by the coordinator's SpotCheckService and stored on the shadow job
    # record, never accepted from clients.
