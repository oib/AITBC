from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from .decentralized_memory import MemoryType, StorageStatus

class MemoryNodeCreate(BaseModel):
    agent_id: str
    memory_type: MemoryType
    is_encrypted: bool = True
    metadata: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

class MemoryNodeResponse(BaseModel):
    id: str
    agent_id: str
    memory_type: MemoryType
    cid: Optional[str]
    size_bytes: Optional[int]
    is_encrypted: bool
    status: StorageStatus
    metadata: Dict[str, str]
    tags: List[str]
    
    class Config:
        orm_mode = True

class MemoryQueryRequest(BaseModel):
    agent_id: str
    memory_type: Optional[MemoryType] = None
    tags: Optional[List[str]] = None
