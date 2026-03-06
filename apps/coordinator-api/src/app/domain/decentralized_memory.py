"""
Decentralized Memory Domain Models

Domain models for managing agent memory and knowledge graphs on IPFS/Filecoin.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, Relationship

class MemoryType(str, Enum):
    VECTOR_DB = "vector_db"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    POLICY_WEIGHTS = "policy_weights"
    EPISODIC = "episodic"

class StorageStatus(str, Enum):
    PENDING = "pending"         # Upload to IPFS pending
    UPLOADED = "uploaded"       # Available on IPFS
    PINNED = "pinned"           # Pinned on Filecoin/Pinata
    ANCHORED = "anchored"       # CID written to blockchain
    FAILED = "failed"           # Upload failed

class AgentMemoryNode(SQLModel, table=True):
    """Represents a chunk of memory or knowledge stored on decentralized storage"""
    __tablename__ = "agent_memory_node"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    agent_id: str = Field(index=True)
    memory_type: MemoryType = Field(index=True)
    
    # Decentralized Storage Identifiers
    cid: Optional[str] = Field(default=None, index=True) # IPFS Content Identifier
    size_bytes: Optional[int] = Field(default=None)
    
    # Encryption and Security
    is_encrypted: bool = Field(default=True)
    encryption_key_id: Optional[str] = Field(default=None) # Reference to KMS or Lit Protocol
    zk_proof_hash: Optional[str] = Field(default=None) # Hash of the ZK proof verifying content validity
    
    status: StorageStatus = Field(default=StorageStatus.PENDING, index=True)
    
    meta_data: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    # Blockchain Anchoring
    anchor_tx_hash: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
