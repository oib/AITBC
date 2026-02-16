from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, List
from base64 import b64encode, b64decode
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

from .types import JobState, Constraints


# Payment schemas
class JobPaymentCreate(BaseModel):
    """Request to create a payment for a job"""
    job_id: str
    amount: float
    currency: str = "AITBC"  # Jobs paid with AITBC tokens
    payment_method: str = "aitbc_token"  # Primary method for job payments
    escrow_timeout_seconds: int = 3600  # 1 hour default


class JobPaymentView(BaseModel):
    """Payment information for a job"""
    job_id: str
    payment_id: str
    amount: float
    currency: str
    status: str
    payment_method: str
    escrow_address: Optional[str] = None
    refund_address: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    released_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    transaction_hash: Optional[str] = None
    refund_transaction_hash: Optional[str] = None


class PaymentRequest(BaseModel):
    """Request to pay for a job"""
    job_id: str
    amount: float
    currency: str = "BTC"
    refund_address: Optional[str] = None


class PaymentReceipt(BaseModel):
    """Receipt for a payment"""
    payment_id: str
    job_id: str
    amount: float
    currency: str
    status: str
    transaction_hash: Optional[str] = None
    created_at: datetime
    verified_at: Optional[datetime] = None


class EscrowRelease(BaseModel):
    """Request to release escrow payment"""
    job_id: str
    payment_id: str
    reason: Optional[str] = None


class RefundRequest(BaseModel):
    """Request to refund a payment"""
    job_id: str
    payment_id: str
    reason: str


# User management schemas
class UserCreate(BaseModel):
    email: str
    username: str
    password: Optional[str] = None

class UserLogin(BaseModel):
    wallet_address: str
    signature: Optional[str] = None

class UserProfile(BaseModel):
    user_id: str
    email: str
    username: str
    created_at: str
    session_token: Optional[str] = None

class UserBalance(BaseModel):
    user_id: str
    address: str
    balance: float
    updated_at: Optional[str] = None

class Transaction(BaseModel):
    id: str
    type: str
    status: str
    amount: float
    fee: float
    description: Optional[str]
    created_at: str
    confirmed_at: Optional[str] = None

class TransactionHistory(BaseModel):
    user_id: str
    transactions: List[Transaction]
    total: int

class ExchangePaymentRequest(BaseModel):
    user_id: str
    aitbc_amount: float
    btc_amount: float

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
    tx_hash: Optional[str] = None
    confirmed_at: Optional[int] = None

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
    payload: Dict[str, Any]
    constraints: Constraints = Field(default_factory=Constraints)
    ttl_seconds: int = 900
    payment_amount: Optional[float] = None  # Amount to pay for the job
    payment_currency: str = "AITBC"  # Jobs paid with AITBC tokens


class JobView(BaseModel):
    job_id: str
    state: JobState
    assigned_miner_id: Optional[str] = None
    requested_at: datetime
    expires_at: datetime
    error: Optional[str] = None
    payment_id: Optional[str] = None
    payment_status: Optional[str] = None


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
    gpu_model: Optional[str] = None
    gpu_memory_gb: Optional[int] = None
    gpu_count: Optional[int] = 1
    cuda_version: Optional[str] = None
    price_per_hour: Optional[float] = None
    region: Optional[str] = None
    attributes: Optional[dict] = None


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


class MarketplaceBidView(BaseModel):
    id: str
    provider: str
    capacity: int
    price: float
    notes: Optional[str] = None
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
    jobId: Optional[str] = None
    miner: str
    coordinator: str
    issuedAt: datetime
    status: str
    payload: Optional[Dict[str, Any]] = None


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
    payload: Optional[Dict[str, Any]] = None


# Confidential Transaction Models

class ConfidentialTransaction(BaseModel):
    """Transaction with optional confidential fields"""
    
    # Public fields (always visible)
    transaction_id: str
    job_id: str
    timestamp: datetime
    status: str
    
    # Confidential fields (encrypted when opt-in)
    amount: Optional[str] = None
    pricing: Optional[Dict[str, Any]] = None
    settlement_details: Optional[Dict[str, Any]] = None
    
    # Encryption metadata
    confidential: bool = False
    encrypted_data: Optional[str] = None  # Base64 encoded
    encrypted_keys: Optional[Dict[str, str]] = None  # Base64 encoded
    algorithm: Optional[str] = None
    
    # Access control
    participants: List[str] = []
    access_policies: Dict[str, Any] = {}
    
    model_config = ConfigDict(populate_by_name=True)


class ConfidentialTransactionCreate(BaseModel):
    """Request to create confidential transaction"""
    
    job_id: str
    amount: Optional[str] = None
    pricing: Optional[Dict[str, Any]] = None
    settlement_details: Optional[Dict[str, Any]] = None
    
    # Privacy options
    confidential: bool = False
    participants: List[str] = []
    
    # Access policies
    access_policies: Dict[str, Any] = {}


class ConfidentialTransactionView(BaseModel):
    """Response for confidential transaction view"""
    
    transaction_id: str
    job_id: str
    timestamp: datetime
    status: str
    
    # Decrypted fields (only if authorized)
    amount: Optional[str] = None
    pricing: Optional[Dict[str, Any]] = None
    settlement_details: Optional[Dict[str, Any]] = None
    
    # Metadata
    confidential: bool
    participants: List[str]
    has_encrypted_data: bool


class ConfidentialAccessRequest(BaseModel):
    """Request to access confidential transaction data"""
    
    transaction_id: str
    requester: str
    purpose: str
    justification: Optional[str] = None


class ConfidentialAccessResponse(BaseModel):
    """Response for confidential data access"""
    
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    access_id: Optional[str] = None


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
    error: Optional[str] = None


# Access Log Models

class ConfidentialAccessLog(BaseModel):
    """Audit log for confidential data access"""
    
    transaction_id: Optional[str]
    participant_id: str
    purpose: str
    timestamp: datetime
    authorized_by: str
    data_accessed: List[str]
    success: bool
    error: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AccessLogQuery(BaseModel):
    """Query for access logs"""
    
    transaction_id: Optional[str] = None
    participant_id: Optional[str] = None
    purpose: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class AccessLogResponse(BaseModel):
    """Response for access log query"""
    
    logs: List[ConfidentialAccessLog]
    total_count: int
    has_more: bool
