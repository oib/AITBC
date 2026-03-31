
from pydantic import BaseModel, Field

from .decentralized_memory import MemoryType, StorageStatus


class MemoryNodeCreate(BaseModel):
    agent_id: str
    memory_type: MemoryType
    is_encrypted: bool = True
    metadata: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class MemoryNodeResponse(BaseModel):
    id: str
    agent_id: str
    memory_type: MemoryType
    cid: str | None
    size_bytes: int | None
    is_encrypted: bool
    status: StorageStatus
    metadata: dict[str, str]
    tags: list[str]

    class Config:
        orm_mode = True


class MemoryQueryRequest(BaseModel):
    agent_id: str
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
