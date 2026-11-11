"""
Decentralized Memory Domain Models

Domain models for managing agent memory and knowledge graphs on IPFS/Filecoin.
"""

from __future__ import annotations

from enum import StrEnum


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


__all__ = []
