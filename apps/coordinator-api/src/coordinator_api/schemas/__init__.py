from __future__ import annotations

import re
from base64 import b64decode, b64encode
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from aitbc_agent_core import get_active_brand
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..custom_types import Constraints, JobState

_brand = get_active_brand()
# str() because the getattr fallback is the BrandSettings object itself, and both
# uses below are declared `str`.
brand_symbol = str(getattr(_brand, "token_symbol", _brand))


# Payment schemas
class JobPaymentCreate(BaseModel):
    """Request to create a payment for a job"""

    job_id: str = Field(..., min_length=1, max_length=128, description="Job identifier")
    amount: Decimal = Field(..., gt=Decimal("0"), le=Decimal("1000000"), description=f"Payment amount in {brand_symbol}")
    currency: str = Field(default=brand_symbol, description="Payment currency")
    payment_method: str = Field(default="aitbc_token", description="Payment method")
    escrow_timeout_seconds: int = Field(default=3600, ge=300, le=86400, description="Escrow timeout in seconds")
    buyer_address: str | None = Field(default=None, description="Customer wallet address for escrow")
    provider_address: str | None = Field(default=None, description="Provider wallet address for escrow")
    buyer_lock_signature: str | None = Field(default=None, description="Pre-signed ESCROW_LOCK transaction signature")
    buyer_lock_nonce: int | None = Field(default=None, description="Nonce used in the ESCROW_LOCK transaction")
    buyer_lock_fee: int | None = Field(default=None, description="Fee used in the ESCROW_LOCK transaction")
    auto_reinvest_pct: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("100"), description="Percentage of released payment to auto-stake"
    )
    # G1: the quote this amount came from, kept so a settlement can be audited against
    # what was advertised rather than only against what was charged.
    offer_id: str | None = Field(default=None, description="Marketplace offer the amount was quoted from")
    offer_unit_price: Decimal | None = Field(default=None, description="Advertised price of one unit")
    offer_price_unit: str | None = Field(default=None, description="Unit the offer is priced in")
    offer_quantity: Decimal | None = Field(default=None, description="Units bought at the advertised price")

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        """Validate job ID format to prevent injection attacks"""
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError("Job ID contains invalid characters")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Validate and round payment amount"""
        if v < Decimal("0.01"):
            raise ValueError("Minimum payment amount is 0.01 AITBC")
        return round(v, 8)  # Prevent floating point precision issues

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code"""
        allowed_currencies = ["AITBC", "ETH", "USDT"]
        if v.upper() not in allowed_currencies:
            raise ValueError(f"Currency must be one of: {allowed_currencies}")
        return v.upper()


class JobPaymentView(BaseModel):
    """Payment information for a job"""

    job_id: str
    payment_id: str
    amount: Decimal
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
    amount: Decimal = Field(..., gt=Decimal("0"), le=Decimal("1000000"), description="Payment amount")
    currency: str = Field(default="ETH", description="Payment currency")
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
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Validate payment amount"""
        if v < Decimal("0.0001"):  # Minimum ETH amount
            raise ValueError("Minimum payment amount is 0.0001 ETH")
        return round(v, 8)

    @field_validator("refund_address")
    @classmethod
    def validate_refund_address(cls, v: str | None) -> str | None:
        """Validate refund address format"""
        if v is None:
            return v
        # Basic Ethereum / AITBC address validation
        if not re.match(r"^0x[a-fA-F0-9]{40}$", v):
            raise ValueError("Invalid Ethereum address format")
        return v


class PaymentReceipt(BaseModel):
    """Receipt for a payment"""

    payment_id: str
    job_id: str
    amount: Decimal
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
    wallet_address: str
    nonce: str
    signature: str


class UserLogin(BaseModel):
    wallet_address: str
    nonce: str
    signature: str


class UserNonceRequest(BaseModel):
    wallet_address: str


class UserNonceResponse(BaseModel):
    wallet_address: str
    nonce: str
    expires_at: int


class UserProfile(BaseModel):
    user_id: str
    email: str
    username: str
    created_at: str
    session_token: str | None = None


class UserBalance(BaseModel):
    user_id: str
    address: str
    balance: Decimal
    updated_at: str | None = None


class Transaction(BaseModel):
    id: str
    type: str
    status: str
    amount: Decimal
    fee: Decimal
    description: str | None
    created_at: str
    confirmed_at: str | None = None


class TransactionHistory(BaseModel):
    user_id: str
    transactions: list[Transaction]
    total: int


class ExchangePaymentRequest(BaseModel):
    """Request for ETH exchange payment"""

    user_id: str = Field(..., min_length=1, max_length=128, description="User identifier")
    aitbc_amount: Decimal = Field(..., gt=0, le=1_000_000, description="AITBC amount to exchange")
    eth_amount: Decimal = Field(..., gt=0, le=10000, description="ETH amount to receive")

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

    @field_validator("eth_amount")
    @classmethod
    def validate_eth_amount(cls, v: float) -> float:
        """Validate ETH amount"""
        if v < 0.0001:
            raise ValueError("Minimum ETH amount is 0.0001")
        return round(v, 8)

    @model_validator(mode="after")
    def validate_exchange_ratio(self) -> ExchangePaymentRequest:
        """Validate that the exchange ratio is reasonable"""
        if self.aitbc_amount > 0 and self.eth_amount > 0:
            ratio = self.aitbc_amount / self.eth_amount
            # AITBC/ETH ratio should be reasonable (e.g., 1,000 AITBC = 1 ETH)
            if ratio < 10 or ratio > 100000:
                raise ValueError("Exchange ratio is outside reasonable bounds")
        return self


class ExchangePaymentResponse(BaseModel):
    payment_id: str
    user_id: str
    aitbc_amount: Decimal
    eth_amount: Decimal
    payment_address: str
    status: str
    created_at: int
    expires_at: int


class ExchangeRatesResponse(BaseModel):
    eth_to_aitbc: Decimal
    aitbc_to_eth: Decimal
    fee_percent: float


class PaymentStatusResponse(BaseModel):
    payment_id: str
    user_id: str
    aitbc_amount: Decimal
    eth_amount: Decimal
    payment_address: str
    status: str
    created_at: int
    expires_at: int
    confirmations: int = 0
    tx_hash: str | None = None
    confirmed_at: int | None = None


class MarketStatsResponse(BaseModel):
    price: Decimal
    price_change_24h: Decimal
    daily_volume: Decimal
    daily_volume_eth: Decimal
    total_payments: int
    pending_payments: int


class JobCreate(BaseModel):
    payload: dict[str, Any]
    constraints: Constraints = Field(default_factory=Constraints)
    ttl_seconds: int = 900
    payment_amount: Decimal | None = None  # Amount to pay for the job
    payment_currency: str = brand_symbol  # Jobs paid with network tokens
    buyer_address: str | None = None  # Customer wallet address for escrow
    provider_address: str | None = None  # Provider wallet address for escrow
    # G1: the marketplace listing this job is bought against. When set, the offer
    # decides the price and the payee, and a payment_amount or provider_address that
    # disagrees with it is refused rather than quietly preferred.
    offer_id: str | None = Field(default=None, description="Marketplace offer this job is bought against")
    offer_quantity: Decimal = Field(
        default=Decimal("1"),
        gt=Decimal("0"),
        description="How many of the offer's price_unit are being bought",
    )


class JobView(BaseModel):
    # v0.24.0: include payload and result so dashboards can show model and output
    job_id: str
    state: JobState
    assigned_miner_id: str | None = None
    requested_at: datetime | None = None
    expires_at: datetime | None = None
    error: str | None = None
    payment_id: str | None = None
    payment_status: str | None = None
    # G1: the offer that priced and routed this job, surfaced so clients can audit it.
    offer_id: str | None = None
    offer_unit_price: Decimal | None = None
    offer_price_unit: str | None = None
    offer_quantity: Decimal | None = None
    zk_status: str | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    zk_proof_id: str | None = None
    tee_status: str | None = None
    tee_attestation_id: str | None = None
    auto_reinvest_pct: Decimal | None = None
    reinvest_status: str | None = None
    reinvest_stake_id: str | None = None
    # G3: when the held escrow releases on its own if the customer says nothing.
    acceptance_deadline: datetime | None = None


class JobRejection(BaseModel):
    """A customer's refusal of a delivered result."""

    reason: str = Field(min_length=1, max_length=500, description="Why the result is being refused")


class DisputeResolution(BaseModel):
    """An operator's or arbiter's ruling on a disputed payment."""

    outcome: Literal["refund", "release"] = Field(description="Whether the escrow returns to the buyer or pays the provider")
    reason: str = Field(min_length=1, max_length=500, description="The ruling, recorded on the settlement")


class JobResult(BaseModel):
    result: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None


class MinerRegister(BaseModel):
    capabilities: dict[str, Any]
    concurrency: int = 1
    region: str | None = None
    # G2: the address escrow releases pay out to. A miner that declares none cannot
    # be matched against an escrow's provider and so will not be given escrowed work.
    wallet_address: str | None = Field(default=None, description="Payout wallet address for escrow releases")


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
    tee_attestation_id: str | None = Field(default=None, description="Existing TEE attestation ID")
    tee_quote: str | None = Field(default=None, description="Base64 TEE attestation quote to verify")


class JobFailSubmit(BaseModel):
    error_code: str
    error_message: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class MarketplaceOfferView(BaseModel):
    id: str
    provider: str
    capacity: int
    price: Decimal
    sla: str
    status: str
    created_at: datetime
    gpu_model: str | None = None
    gpu_memory_gb: int | None = None
    gpu_count: int | None = 1
    cuda_version: str | None = None
    price_per_hour: Decimal | None = None
    region: str | None = None
    attributes: dict[str, Any] | None = None


class MarketplaceStatsView(BaseModel):
    totalOffers: int
    openCapacity: int
    averagePrice: Decimal
    activeBids: int


# Bids deprecated in v0.4.7 - GPU-only marketplace removed
# MarketplaceBidRequest and MarketplaceBidView no longer available


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
    model_config = ConfigDict(populate_by_name=True)

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
