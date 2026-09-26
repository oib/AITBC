from __future__ import annotations

from aitbc_shared import MarketOffer
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field

from .base import MarketBase

# Re-export MarketOffer from aitbc_shared for compatibility
__all__ = ["MarketOffer"]


# Additional market-specific models
class Plugin(MarketBase, table=True):
    __tablename__ = "plugin"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    author: str = Field(default="")
    type: str = Field(default="cli", index=True)  # cli, web, blockchain, ai
    version: str = Field(default="1.0.0")
    ipfs_cid: str | None = Field(default=None, index=True)  # IPFS CID for plugin code
    plugin_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", index=True)  # pending, approved, rejected
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    download_count: int = Field(default=0)
    rating: float = Field(default=0.0)


class SoftwareService(MarketBase, table=True):
    """Software service registry for market (migrated from plugin service)"""

    __tablename__ = "softwareservice"

    plugin_id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    service_type: str = Field(index=True)  # ollama, whisper, ffmpeg, hermes, ipfs, cloud_ollama
    model: str = Field(default="", index=True)
    price: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(20, 8)))
    price_unit: str = Field(default="per_1k_tokens")  # per_1k_tokens, per_audio_min, per_processing_hour, per_day, per_minute
    offer_id: str | None = Field(default=None, index=True)  # Live offer_id from hub
    endpoint: str = Field(default="")  # Local endpoint
    public_endpoint: str = Field(default="")  # Public endpoint
    health_url: str = Field(default="")
    provider_address: str = Field(default="", index=True)
    node_id: str = Field(default="")
    gpu_name: str = Field(default="")  # GPU name from nvidia-smi
    gpu_device: str = Field(default="0")  # GPU device ID (0, 1, 2, etc.)
    gpu_uuid: str | None = Field(default=None)  # GPU UUID from nvidia-smi
    gpu_offer_id: str | None = Field(default=None)  # GPU market offer ID
    gpu_model: str | None = Field(default=None)  # GPU model name
    gpu_memory_gb: int | None = Field(default=None)  # GPU memory in GB
    compute_capability: str | None = Field(default=None)  # CUDA compute capability
    description: str = Field(default="")
    status: str = Field(default="active", index=True)  # active, inactive
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    disk_quota_mb: int | None = Field(default=None)  # Per-customer disk quota (e.g. 100 MB for IPFS)
    avg_rating: float = Field(default=0.0)  # Average service rating (1-5 scale)
    rating_count: int = Field(default=0)  # Number of ratings received
    # Blockchain-related fields
    block_height: int | None = Field(default=None)
    block_hash: str | None = Field(default=None)
    tx_hash: str | None = Field(default=None)
    block_proposer: str | None = Field(default=None)
    block_timestamp: datetime | None = Field(default=None)


class OfferAnchor(MarketBase, table=True):
    """Stored on-chain anchor confirmation for a market offer.

    Written only by the server, from a verified anchor transaction — the
    namespaced key and provider binding are the same rules
    ``_resolve_offer_anchors`` applies live, so a stored row means the offer
    once resolved to a sealed tx authored by its provider. Rows persist the
    confirmation for offers that have no local ``SoftwareService`` row
    (on-chain GPU offers) and let listings skip the per-request transaction
    RPCs once confirmation has been found. If the offer's binding identity
    changes (e.g. a GPU row gains ``registered_by`` after an RPC upgrade)
    the row is re-resolved live and rewritten.
    """

    __tablename__ = "offer_anchor"

    key: str = Field(primary_key=True)  # namespaced: "gpu:<gpu_id>" or "offer:<offer_id>"
    tx_hash: str = Field(default="")
    block_height: int | None = Field(default=None)
    block_hash: str | None = Field(default=None)
    block_proposer: str | None = Field(default=None)
    # Verbatim tx strings (not datetimes): the offer dict emits them raw, so
    # storing the original form keeps stored-confirmation output identical
    # to live resolution instead of re-serializing through naive datetimes.
    block_timestamp: str | None = Field(default=None)
    registered_at: str | None = Field(default=None)  # anchor tx created_at — the GPU offer's registration time
    bound_provider: str = Field(default="", index=True)  # the offer-side identity the anchor was verified against
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)


class Bid(MarketBase, table=True):
    """Bid/offer booking record."""

    __tablename__ = "bids"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    offer_id: str = Field(index=True)
    provider: str = Field(default="", index=True)
    buyer: str = Field(default="", index=True)
    capacity: float = Field(default=0.0)
    price: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(20, 8)))
    status: str = Field(default="pending", index=True)  # pending, completed, active, cancelled
    tx_hash: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)


class IpfsRentalToken(MarketBase, table=True):
    """Access token for a paid IPFS rental."""

    __tablename__ = "ipfs_rental_token"

    access_key: str = Field(primary_key=True)
    access_secret: str = Field(index=True)
    rental_id: str = Field(default="", index=True)
    offer_id: str = Field(default="", index=True)
    cid: str = Field(default="", index=True)
    buyer_address: str = Field(default="", index=True)
    provider_address: str = Field(default="", index=True)
    escrow_contract_id: str = Field(default="")
    ipfs_api: str = Field(default="")
    public_endpoint: str = Field(default="")
    disk_quota_mb: int | None = Field(default=None)
    size: int | None = Field(default=None)
    pinned: bool = Field(default=True)  # whether the provider pinned the CID
    status: str = Field(default="active", index=True)  # active, expired, refunded, released, refund_pending
    tx_hash: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    expires_at: datetime | None = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)


class MarketJob(MarketBase, table=True):
    """Generic job record for a paid market software service."""

    __tablename__ = "marketplace_jobs"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    client_id: str | None = Field(default=None, index=True)
    client_ref: str | None = Field(default=None, index=True)

    # Offer / service linkage
    offer_id: str | None = Field(default=None, index=True)
    plugin_id: str | None = Field(default=None, index=True)
    service_type: str | None = Field(default=None, index=True)
    model: str | None = Field(default=None)

    # Parties
    buyer_address: str | None = Field(default=None, index=True)
    provider_address: str | None = Field(default=None, index=True)

    # Lifecycle
    state: str = Field(default="QUEUED", max_length=20, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    constraints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    ttl_seconds: int = Field(default=2_592_000)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    expires_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    error: str | None = Field(default=None)

    # Result / receipt
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    receipt: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # Access token for this job (e.g. IPFS access key)
    access_key: str | None = Field(default=None, index=True)

    # Payment denormalization (authoritative source is MarketJobPayment)
    payment_id: str | None = Field(default=None, index=True)
    payment_status: str | None = Field(default=None, max_length=20)
    payment_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(36, 18)))
    payment_token: str | None = Field(default=None, max_length=42)

    # Escrow linkage
    escrow_contract_id: str | None = Field(default=None, index=True)
    tx_hash: str | None = Field(default=None)
    refund_tx_hash: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)


class MarketJobPayment(MarketBase, table=True):
    """Payment record for a MarketJob."""

    __tablename__ = "marketplace_job_payments"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    job_id: str = Field(index=True)

    # Payment details
    amount: Decimal = Field(sa_column=Column(Numeric(20, 8), nullable=False))
    currency: str = Field(default="AITBC", max_length=10)
    status: str = Field(default="pending", max_length=20)
    payment_method: str = Field(default="aitbc_token", max_length=20)

    # Addresses
    escrow_address: str | None = Field(default=None)
    refund_address: str | None = Field(default=None)

    # Transaction hashes
    transaction_hash: str | None = Field(default=None)
    refund_transaction_hash: str | None = Field(default=None)

    # Settlement amounts for metered releases/refunds
    released_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(20, 8), nullable=True))
    refunded_amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(20, 8), nullable=True))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    escrowed_at: datetime | None = Field(default=None)
    released_at: datetime | None = Field(default=None)
    refunded_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)

    # Additional metadata
    meta_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))


class ServiceRating(MarketBase, table=True):
    """Service-specific ratings for market offers"""

    __tablename__ = "servicerating"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    service_id: str = Field(index=True)  # Foreign key to SoftwareService.plugin_id
    rating: float = Field(default=0.0)  # Rating value (1-5 scale)
    reviewer_id: str = Field(index=True)  # ID of the user providing the rating
    comment: str = Field(default="")  # Optional comment/review text
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    synced_at: datetime | None = Field(default=None, nullable=True)  # Last sync timestamp
    source_node: str = Field(default="local", index=True)  # Origin node of the rating


class KnowledgeGraph(MarketBase, table=True):
    __tablename__ = "knowledgegraph"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    owner: str = Field(index=True)
    status: str = Field(default="active", index=True)  # active, archived, deleted
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)


class GraphNode(MarketBase, table=True):
    __tablename__ = "graphnode"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    graph_id: str = Field(index=True)
    node_type: str = Field(index=True)  # entity, concept, relation, etc.
    label: str = Field(index=True)
    properties: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)


class GraphEdge(MarketBase, table=True):
    __tablename__ = "graphedge"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    graph_id: str = Field(index=True)
    source_node_id: str = Field(index=True)
    target_node_id: str = Field(index=True)
    edge_type: str = Field(index=True)  # relates_to, depends_on, etc.
    properties: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    weight: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)


class EdgeNodeAdvertisement(MarketBase, table=True):
    """Edge node advertisement registered via POST /v1/market/edge-advertise (v0.6.6)."""

    __tablename__ = "edge_node_advertisements"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    node_id: str = Field(index=True, unique=True)
    endpoint: str = Field(default="")
    node_type: str = Field(default="edge")
    service: str = Field(default="aitbc-edge")
    gpu_models: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    gpu_count: int = Field(default=0)
    total_vram: int = Field(default=0)
    region: str = Field(default="", index=True)
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    health_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_health_check: datetime | None = Field(default=None)
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False, index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
