"""Durable cid -> agent ownership for IPFS memories (#2711).

The IPFSService registries are process-local OrderedDicts: after a restart or
an LRU eviction the owner of a CID is unresolvable and the #1882 ownership
bind fails closed for the legitimate owner. This table is the persistent
record written at upload time and consulted on cache misses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class IPFSMemoryOwner(SQLModel, table=True):
    __tablename__ = "ipfs_memory_owner"

    cid: str = Field(primary_key=True)
    agent_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
