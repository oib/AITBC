from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class MarketplaceOffer(SQLModel, table=True):
    __tablename__ = "marketplaceoffer"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    provider: str | None = Field(default=None, index=True)
    capacity: int = Field(default=0, nullable=False)
    price: float = Field(default=0.0, nullable=False)
    sla: str = Field(default="")
    status: str = Field(default="open", max_length=20)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    attributes: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # GPU-specific fields
    gpu_model: str | None = Field(default=None, index=True)
    gpu_memory_gb: int | None = Field(default=None)
    gpu_count: int | None = Field(default=1)
    cuda_version: str | None = Field(default=None)
    price_per_hour: float | None = Field(default=None)
    region: str | None = Field(default=None, index=True)




class Plugin(SQLModel, table=True):
    __tablename__ = "plugin"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    author: str = Field(default="")
    type: str = Field(default="cli", index=True)  # cli, web, blockchain, ai
    version: str = Field(default="1.0.0")
    ipfs_cid: str | None = Field(default=None, index=True)  # IPFS CID for plugin code
    plugin_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", index=True)  # pending, approved, rejected
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    download_count: int = Field(default=0)
    rating: float = Field(default=0.0)


class SoftwareService(SQLModel, table=True):
    """Software service registry for marketplace (migrated from plugin service)"""
    __tablename__ = "softwareservice"
    __table_args__ = {"extend_existing": True}

    plugin_id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    service_type: str = Field(index=True)  # ollama, whisper, ffmpeg, peertube_transcoder
    model: str = Field(default="", index=True)
    price: float = Field(default=0.0)
    price_unit: str = Field(default="per_1k_tokens")  # per_1k_tokens, per_audio_min, per_processing_hour
    offer_id: str | None = Field(default=None, index=True)  # Live offer_id from hub
    endpoint: str = Field(default="")  # Local endpoint
    public_endpoint: str = Field(default="")  # Public endpoint
    health_url: str = Field(default="")
    provider_address: str = Field(default="", index=True)
    node_id: str = Field(default="")
    gpu_name: str = Field(default="")  # GPU name from nvidia-smi
    gpu_device: str = Field(default="0")  # GPU device ID (0, 1, 2, etc.)
    gpu_uuid: str | None = Field(default=None)  # GPU UUID from nvidia-smi
    gpu_offer_id: str | None = Field(default=None)  # GPU marketplace offer ID
    description: str = Field(default="")
    status: str = Field(default="active", index=True)  # active, inactive
    registered_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class KnowledgeGraph(SQLModel, table=True):
    __tablename__ = "knowledgegraph"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    owner: str = Field(index=True)
    status: str = Field(default="active", index=True)  # active, archived, deleted
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class GraphNode(SQLModel, table=True):
    __tablename__ = "graphnode"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    graph_id: str = Field(index=True)
    node_type: str = Field(index=True)  # entity, concept, relation, etc.
    label: str = Field(index=True)
    properties: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class GraphEdge(SQLModel, table=True):
    __tablename__ = "graphedge"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    graph_id: str = Field(index=True)
    source_node_id: str = Field(index=True)
    target_node_id: str = Field(index=True)
    edge_type: str = Field(index=True)  # relates_to, depends_on, etc.
    properties: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    weight: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
