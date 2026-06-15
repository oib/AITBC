"""Dispute-related Pydantic models for RPC endpoints."""

from typing import Any

from pydantic import BaseModel


class FileDisputeRequest(BaseModel):
    agreement_id: int
    respondent: str
    dispute_type: str
    reason: str
    evidence_hash: str


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
    vote: str  # "plaintiff" or "defendant"
    reasoning: str


class SubmitArbitrationVoteResponse(BaseModel):
    status: str
    vote_id: int


class AuthorizeArbitratorRequest(BaseModel):
    arbitrator_address: str
    authorized: bool


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
