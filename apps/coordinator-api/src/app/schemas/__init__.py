from __future__ import annotations

import re
from base64 import b64decode, b64encode
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..custom_types import Constraints, JobState


# Payment schemas
class JobPaymentCreate(BaseModel):
    """Request to create a payment for a job"""

    job_id: str = Field(..., min_length=1, max_length=128, description="Job identifier")
    amount: float = Field(..., gt=0, le=1_000_000, description="Payment amount in AITBC")
    currency: str = Field(default="AITBC", description="Payment currency")
    payment_method: str = Field(default="aitbc_token", description="Payment method")
    escrow_timeout_seconds: int = Field(default=3600, ge=300, le=86400, description="Escrow timeout in seconds")

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        """Validate job ID format to prevent injection attacks"""
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError("Job ID contains invalid characters")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Validate and round payment amount"""
        if v < 0.01:
            raise ValueError("Minimum payment amount is 0.01 AITBC")
        return round(v, 8)  # Prevent floating point precision issues

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code"""
        allowed_currencies = ["AITBC", "BTC", "ETH", "USDT"]
        if v.upper() not in allowed_currencies:
            raise ValueError(f"Currency must be one of: {allowed_currencies}")
        return v.upper()


class JobPaymentView(BaseModel):
    """Payment information for a job"""

    job_id: str
    payment_id: str
    amount: float
    currency: str
    status: str
    payment_method: str
    escrow_address: str | None = None
    refund_address: str | None = None
    created_at: datetime
    updated_at: datetime
    released_at: datetime | None = None
    refunded_at: datetime | None = None
    transaction_hash: str | None = None
    refund_transaction_hash: str | None = None


class PaymentRequest(BaseModel):
    """Request to pay for a job"""

    job_id: str = Field(..., min_length=1, max_length=128, description="Job identifier")
    amount: float = Field(..., gt=0, le=1_000_000, description="Payment amount")
    currency: str = Field(default="BTC", description="Payment currency")
    refund_address: str | None = Field(None, min_length=1, max_length=255, description="Refund address")

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        """Validate job ID format"""
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError("Job ID contains invalid characters")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Validate payment amount"""
        if v < 0.0001:  # Minimum BTC amount
            raise ValueError("Minimum payment amount is 0.0001")
        return round(v, 8)

    @field_validator("refund_address")
    @classmethod
    def validate_refund_address(cls, v: str | None) -> str | None:
        """Validate refund address format"""
        if v is None:
            return v
        # Basic Bitcoin address validation
        if not re.match(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{8,87}$", v):
            raise ValueError("Invalid Bitcoin address format")
        return v


class PaymentReceipt(BaseModel):
    """Receipt for a payment"""

    payment_id: str
    job_id: str
    amount: float
    currency: str
    status: str
    transaction_hash: str | None = None
    created_at: datetime
    verified_at: datetime | None = None


class EscrowRelease(BaseModel):
    """Request to release escrow payment"""

    job_id: str
    payment_id: str
    reason: str | None = None


class RefundRequest(BaseModel):
    """Request to refund a payment"""

    job_id: str
    payment_id: str
    reason: str


# User management schemas
class UserCreate(BaseModel):
    email: str
    username: str
    password: str | None = None


class UserLogin(BaseModel):
    wallet_address: str
    signature: str | None = None


class UserProfile(BaseModel):
    user_id: str
    email: str
    username: str
    created_at: str
    session_token: str | None = None


class UserBalance(BaseModel):
    user_id: str
    address: str
    balance: float
    updated_at: str | None = None


class Transaction(BaseModel):
    id: str
    type: str
    status: str
    amount: float
    fee: float
    description: str | None
    created_at: str
    confirmed_at: str | None = None


class TransactionHistory(BaseModel):
    user_id: str
    transactions: list[Transaction]
    total: int


class ExchangePaymentRequest(BaseModel):
    """Request for Bitcoin exchange payment"""

    user_id: str = Field(..., min_length=1, max_length=128, description="User identifier")
    aitbc_amount: float = Field(..., gt=0, le=1_000_000, description="AITBC amount to exchange")
    btc_amount: float = Field(..., gt=0, le=100, description="BTC amount to receive")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Validate user ID format"""
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError("User ID contains invalid characters")
        return v

    @field_validator("aitbc_amount")
    @classmethod
    def validate_aitbc_amount(cls, v: float) -> float:
        """Validate AITBC amount"""
        if v < 0.01:
            raise ValueError("Minimum AITBC amount is 0.01")
        return round(v, 8)

    @field_validator("btc_amount")
    @classmethod
    def validate_btc_amount(cls, v: float) -> float:
        """Validate BTC amount"""
        if v < 0.0001:
            raise ValueError("Minimum BTC amount is 0.0001")
        return round(v, 8)

    @model_validator(mode="after")
    def validate_exchange_ratio(self) -> ExchangePaymentRequest:
        """Validate that the exchange ratio is reasonable"""
        if self.aitbc_amount > 0 and self.btc_amount > 0:
            ratio = self.aitbc_amount / self.btc_amount
            # AITBC/BTC ratio should be reasonable (e.g., 100,000 AITBC = 1 BTC)
            if ratio < 1000 or ratio > 1000000:
                raise ValueError("Exchange ratio is outside reasonable bounds")
        return self


class ExchangePaymentResponse(BaseModel):
    payment_id: str
    user_id: str
    aitbc_amount: float
    btc_amount: float
    payment_address: str
    status: str
    created_at: int
    expires_at: int


class ExchangeRatesResponse(BaseModel):
    btc_to_aitbc: float
    aitbc_to_btc: float
    fee_percent: float


class PaymentStatusResponse(BaseModel):
    payment_id: str
    user_id: str
    aitbc_amount: float
    btc_amount: float
    payment_address: str
    status: str
    created_at: int
    expires_at: int
    confirmations: int = 0
    tx_hash: str | None = None
    confirmed_at: int | None = None


class MarketStatsResponse(BaseModel):
    price: float
    price_change_24h: float
    daily_volume: float
    daily_volume_btc: float
    total_payments: int
    pending_payments: int


class WalletBalanceResponse(BaseModel):
    address: str
    balance: float
    unconfirmed_balance: float
    total_received: float
    total_sent: float


class WalletInfoResponse(BaseModel):
    address: str
    balance: float
    unconfirmed_balance: float
    total_received: float
    total_sent: float
    transactions: list
    network: str
    block_height: int


class JobCreate(BaseModel):
    payload: dict[str, Any]
    constraints: Constraints = Field(default_factory=Constraints)
    ttl_seconds: int = 900
    payment_amount: float | None = None  # Amount to pay for the job
    payment_currency: str = "AITBC"  # Jobs paid with AITBC tokens


class JobView(BaseModel):
    job_id: str
    state: JobState
    assigned_miner_id: str | None = None
    requested_at: datetime
    expires_at: datetime
    error: str | None = None
    payment_id: str | None = None
    payment_status: str | None = None


class JobResult(BaseModel):
    result: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None


class MinerRegister(BaseModel):
    capabilities: dict[str, Any]
    concurrency: int = 1
    region: str | None = None


class MinerHeartbeat(BaseModel):
    inflight: int = 0
    status: str = "ONLINE"
    metadata: dict[str, Any] = Field(default_factory=dict)
    architecture: str | None = None
    edge_optimized: bool | None = None
    network_latency_ms: float | None = None


class PollRequest(BaseModel):
    max_wait_seconds: int = 15


class AssignedJob(BaseModel):
    job_id: str
    payload: dict[str, Any]
    constraints: Constraints


class JobResultSubmit(BaseModel):
    result: dict[str, Any]
    metrics: dict[str, Any] = Field(default_factory=dict)


class JobFailSubmit(BaseModel):
    error_code: str
    error_message: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class MarketplaceOfferView(BaseModel):
    id: str
    provider: str
    capacity: int
    price: float
    sla: str
    status: str
    created_at: datetime
    gpu_model: str | None = None
    gpu_memory_gb: int | None = None
    gpu_count: int | None = 1
    cuda_version: str | None = None
    price_per_hour: float | None = None
    region: str | None = None
    attributes: dict | None = None


class MarketplaceStatsView(BaseModel):
    totalOffers: int
    openCapacity: int
    averagePrice: float
    activeBids: int


class MarketplaceBidRequest(BaseModel):
    provider: str = Field(..., min_length=1)
    capacity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    notes: str | None = Field(default=None, max_length=1024)


class MarketplaceBidView(BaseModel):
    id: str
    provider: str
    capacity: int
    price: float
    notes: str | None = None
    status: str
    submitted_at: datetime


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
    next_offset: str | int | None = None


class TransactionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_tuples=True)

    hash: str
    block: str | int
    from_address: str = Field(alias="from")
    to_address: str | None = Field(default=None, alias="to")
    value: str
    status: str


class TransactionListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[TransactionSummary]
    next_offset: str | int | None = None


class AddressSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    address: str
    balance: str
    txCount: int
    lastActive: datetime
    recentTransactions: list[str] | None = Field(default=None)


class AddressListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[AddressSummary]
    next_offset: str | int | None = None


class ReceiptSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receiptId: str
    jobId: str | None = None
    miner: str
    coordinator: str
    issuedAt: datetime
    status: str
    payload: dict[str, Any] | None = None


class ReceiptListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    jobId: str
    items: list[ReceiptSummary]


class Receipt(BaseModel):
    """Receipt model for zk-proof generation"""

    receiptId: str
    miner: str
    coordinator: str
    issuedAt: datetime
    status: str
    payload: dict[str, Any] | None = None


# Confidential Transaction Models


class ConfidentialTransaction(BaseModel):
    """Transaction with optional confidential fields"""

    # Public fields (always visible)
    transaction_id: str
    job_id: str
    timestamp: datetime
    status: str

    # Confidential fields (encrypted when opt-in)
    amount: str | None = None
    pricing: dict[str, Any] | None = None
    settlement_details: dict[str, Any] | None = None

    # Encryption metadata
    confidential: bool = False
    encrypted_data: str | None = None  # Base64 encoded
    encrypted_keys: dict[str, str] | None = None  # Base64 encoded
    algorithm: str | None = None

    # Access control
    participants: list[str] = []
    access_policies: dict[str, Any] = {}

    model_config = ConfigDict(populate_by_name=True)


class ConfidentialTransactionCreate(BaseModel):
    """Request to create confidential transaction"""

    job_id: str
    amount: str | None = None
    pricing: dict[str, Any] | None = None
    settlement_details: dict[str, Any] | None = None

    # Privacy options
    confidential: bool = False
    participants: list[str] = []

    # Access policies
    access_policies: dict[str, Any] = {}


class ConfidentialTransactionView(BaseModel):
    """Response for confidential transaction view"""

    transaction_id: str
    job_id: str
    timestamp: datetime
    status: str

    # Decrypted fields (only if authorized)
    amount: str | None = None
    pricing: dict[str, Any] | None = None
    settlement_details: dict[str, Any] | None = None

    # Metadata
    confidential: bool
    participants: list[str]
    has_encrypted_data: bool


class ConfidentialAccessRequest(BaseModel):
    """Request to access confidential transaction data"""

    transaction_id: str
    requester: str
    purpose: str
    justification: str | None = None


class ConfidentialAccessResponse(BaseModel):
    """Response for confidential data access"""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    access_id: str | None = None


# Key Management Models


class KeyPair(BaseModel):
    """Encryption key pair for participant"""

    participant_id: str
    private_key: bytes
    public_key: bytes
    algorithm: str = "X25519"
    created_at: datetime
    version: int = 1

    model_config = ConfigDict(arbitrary_types_allowed=True)


class KeyRotationLog(BaseModel):
    """Log of key rotation events"""

    participant_id: str
    old_version: int
    new_version: int
    rotated_at: datetime
    reason: str


class AuditAuthorization(BaseModel):
    """Authorization for audit access"""

    issuer: str
    subject: str
    purpose: str
    created_at: datetime
    expires_at: datetime
    signature: str


class KeyRegistrationRequest(BaseModel):
    """Request to register encryption keys"""

    participant_id: str
    public_key: str  # Base64 encoded
    algorithm: str = "X25519"


class KeyRegistrationResponse(BaseModel):
    """Response for key registration"""

    success: bool
    participant_id: str
    key_version: int
    registered_at: datetime
    error: str | None = None


# Access Log Models


class ConfidentialAccessLog(BaseModel):
    """Audit log for confidential data access"""

    transaction_id: str | None
    participant_id: str
    purpose: str
    timestamp: datetime
    authorized_by: str
    data_accessed: list[str]
    success: bool
    error: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AccessLogQuery(BaseModel):
    """Query for access logs"""

    transaction_id: str | None = None
    participant_id: str | None = None
    purpose: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0


class AccessLogResponse(BaseModel):
    """Response for access log query"""

    logs: list[ConfidentialAccessLog]
    total_count: int
    has_more: bool
