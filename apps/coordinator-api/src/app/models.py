from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict


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


class MarketplaceOfferView(BaseModel):
    id: str
    provider: str
    capacity: int
    price: float
    sla: str
    status: str
    created_at: datetime


class MarketplaceStatsView(BaseModel):
    totalOffers: int
    openCapacity: int
    averagePrice: float
    activeBids: int


class MarketplaceBidRequest(BaseModel):
    provider: str = Field(..., min_length=1)
    capacity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    notes: Optional[str] = Field(default=None, max_length=1024)


class BlockSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    height: int
    hash: str
    timestamp: datetime
    txCount: int
    proposer: str


class BlockListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[BlockSummary]
    next_offset: Optional[str | int] = None


class TransactionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_tuples=True)

    hash: str
    block: str | int
    from_address: str = Field(alias="from")
    to_address: Optional[str] = Field(default=None, alias="to")
    value: str
    status: str


class TransactionListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[TransactionSummary]
    next_offset: Optional[str | int] = None


class AddressSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    address: str
    balance: str
    txCount: int
    lastActive: datetime
    recentTransactions: Optional[list[str]] = Field(default=None)


class AddressListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[AddressSummary]
    next_offset: Optional[str | int] = None


class ReceiptSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receiptId: str
    miner: str
    coordinator: str
    issuedAt: datetime
    status: str
    payload: Optional[Dict[str, Any]] = None


class ReceiptListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    jobId: str
    items: list[ReceiptSummary]
