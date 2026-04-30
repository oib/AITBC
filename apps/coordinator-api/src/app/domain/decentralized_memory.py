"""
Decentralized Memory Domain Models

Domain models for managing agent memory and knowledge graphs on IPFS/Filecoin.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class MemoryType(StrEnum):
    VECTOR_DB = "vector_db"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    POLICY_WEIGHTS = "policy_weights"
    EPISODIC = "episodic"


class StorageStatus(StrEnum):
    PENDING = "pending"  # Upload to IPFS pending
    UPLOADED = "uploaded"  # Available on IPFS
    PINNED = "pinned"  # Pinned on Filecoin/Pinata
    ANCHORED = "anchored"  # CID written to blockchain
    FAILED = "failed"  # Upload failed


class AgentMemoryNode(SQLModel, table=True):
    """Represents a chunk of memory or knowledge stored on decentralized storage"""

    __tablename__ = "agent_memory_node"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    agent_id: str = Field(index=True)
    memory_type: MemoryType = Field(index=True)

    # Decentralized Storage Identifiers
    cid: str | None = Field(default=None, index=True)  # IPFS Content Identifier
    size_bytes: int | None = Field(default=None)

    # Encryption and Security
    is_encrypted: bool = Field(default=True)
    encryption_key_id: str | None = Field(default=None)  # Reference to KMS or Lit Protocol
    zk_proof_hash: str | None = Field(default=None)  # Hash of the ZK proof verifying content validity

    status: StorageStatus = Field(default=StorageStatus.PENDING, index=True)

    meta_data: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Blockchain Anchoring
    anchor_tx_hash: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
