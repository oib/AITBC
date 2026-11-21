"""Dispute-related Pydantic models for RPC endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..contracts.dispute_resolution import DisputeType


class FileDisputeRequest(BaseModel):
    # agreement ids are uint256 on-chain (AIPowerRental.agreementCounter
    # starts at 0), so 0 is valid but negatives can never exist. True
    # existence lives in the coordinator/EVM agreement store — the node has
    # no registry to check against (#2288).
    agreement_id: int = Field(ge=0)
    respondent: str
    dispute_type: str
    reason: str
    evidence_hash: str

    @field_validator("dispute_type")
    @classmethod
    def _dispute_type_must_be_known(cls, value: str) -> str:
        """Reject unknown dispute types at the boundary (422) instead of
        letting ``DisputeType(value)`` raise inside the contract and
        surface as a 500 (#2288)."""
        valid = [t.value for t in DisputeType]
        if value not in valid:
            raise ValueError(f"invalid dispute_type {value!r}; expected one of: {', '.join(valid)}")
        return value


class FileDisputeResponse(BaseModel):
    dispute_id: int
    status: str
    timestamp: str


class SubmitEvidenceRequest(BaseModel):
    dispute_id: int
    evidence_hash: str
    evidence_type: str
    description: str


class SubmitEvidenceResponse(BaseModel):
    evidence_id: int
    status: str


class VerifyEvidenceRequest(BaseModel):
    dispute_id: int
    evidence_id: int
    verified: bool


class VerifyEvidenceResponse(BaseModel):
    status: str


class SubmitArbitrationVoteRequest(BaseModel):
    dispute_id: int
    vote: Literal["plaintiff", "defendant"]  # which side the vote favours
    reasoning: str
    confidence: int = Field(default=100, ge=0, le=100)


class SubmitArbitrationVoteResponse(BaseModel):
    status: str
    vote_id: int


class AuthorizeArbitratorRequest(BaseModel):
    arbitrator_address: str
    authorized: bool
    owner_signature: str | None = None


class AuthorizeArbitratorResponse(BaseModel):
    status: str


class GetDisputeResponse(BaseModel):
    dispute_id: int
    agreement_id: int
    plaintiff: str
    respondent: str
    dispute_type: str
    reason: str
    status: str
    created_at: str
    winner: str | None = None
    resolution_reason: str = ""
    is_escalated: bool = False
    evidence: list[dict[str, Any]] = []
    votes: list[dict[str, Any]] = []


class GetEvidenceResponse(BaseModel):
    evidence_id: int
    dispute_id: int
    evidence_hash: str
    evidence_type: str
    description: str
    submitted_by: str
    verified: bool
    created_at: str


class GetArbitrationVotesResponse(BaseModel):
    dispute_id: int
    votes: list[dict[str, Any]] = []
