

"""
Memory Manager Service for Agent Memory Operations
Handles memory lifecycle management, versioning, and optimization
"""

import asyncio

from aitbc import get_logger

logger = get_logger(__name__)
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .ipfs_storage_service import IPFSStorageService, IPFSUploadResult


class MemoryType(StrEnum):
    """Types of agent memories"""

    EXPERIENCE = "experience"
    POLICY_WEIGHTS = "policy_weights"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    TRAINING_DATA = "training_data"
    USER_FEEDBACK = "user_feedback"
    PERFORMANCE_METRICS = "performance_metrics"
    MODEL_STATE = "model_state"


class MemoryPriority(StrEnum):
    """Memory storage priorities"""

    CRITICAL = "critical"  # Always pin, replicate to all nodes
    HIGH = "high"  # Pin, replicate to majority
    MEDIUM = "medium"  # Pin, selective replication
    LOW = "low"  # No pin, archive only
    TEMPORARY = "temporary"  # No pin, auto-expire


@dataclass
class MemoryConfig:
    """Configuration for memory management"""

    max_memories_per_agent: int = 1000
    batch_upload_size: int = 50
    compression_threshold: int = 1024
    auto_cleanup_days: int = 30
    version_retention: int = 10
    deduplication_enabled: bool = True
    encryption_enabled: bool = True


@dataclass
class MemoryRecord:
    """Record of stored memory"""

    cid: str
    agent_id: str
    memory_type: MemoryType
    priority: MemoryPriority
    version: int
    timestamp: datetime
    size: int
    tags: list[str]
    access_count: int = 0
    last_accessed: datetime | None = None
    expires_at: datetime | None = None
    parent_cid: str | None = None  # For versioning


class MemoryManager:
    """Manager for agent memory operations"""

    def __init__(self, ipfs_service: IPFSStorageService, config: MemoryConfig):
        self.ipfs_service = ipfs_service
        self.config = config
        self.memory_records: dict[str, MemoryRecord] = {}  # In-memory index
        self.agent_memories: dict[str, list[str]] = {}  # agent_id -> [cids]
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize memory manager"""
        logger.info("Initializing Memory Manager")

        # Load existing memory records from database
        await self._load_memory_records()

        # Start cleanup task
        asyncio.create_task(self._cleanup_expired_memories())

        logger.info("Memory Manager initialized")

    async def store_memory(
        self,
        agent_id: str,
        memory_data: Any,
        memory_type: MemoryType,
        priority: MemoryPriority = MemoryPriority.MEDIUM,
        tags: list[str] | None = None,
        version: int | None = None,
        parent_cid: str | None = None,
        expires_in_days: int | None = None,
    ) -> IPFSUploadResult:
        """Store agent memory with versioning and deduplication"""

        async with self._lock:
            try:
                # Check for duplicates if deduplication enabled
                if self.config.deduplication_enabled:
                    existing_cid = await self._find_duplicate_memory(agent_id, memory_data)
                    if existing_cid:
                        logger.info(f"Found duplicate memory for agent {agent_id}: {existing_cid}")
                        await self._update_access_count(existing_cid)
                        return await self._get_upload_result(existing_cid)

                # Determine version
                if version is None:
                    version = await self._get_next_version(agent_id, memory_type, parent_cid)

                # Set expiration for temporary memories
                expires_at = None
                if priority == MemoryPriority.TEMPORARY:
                    expires_at = datetime.utcnow() + timedelta(days=expires_in_days or 7)
                elif expires_in_days:
                    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

                # Determine pinning based on priority
                should_pin = priority in [MemoryPriority.CRITICAL, MemoryPriority.HIGH]

                # Add priority tag
                tags = tags or []
                tags.append(f"priority:{priority.value}")
                tags.append(f"version:{version}")

                # Upload to IPFS
                upload_result = await self.ipfs_service.upload_memory(
                    agent_id=agent_id,
                    memory_data=memory_data,
                    memory_type=memory_type.value,
                    tags=tags,
                    compress=True,
                    pin=should_pin,
                )

                # Create memory record
                memory_record = MemoryRecord(
                    cid=upload_result.cid,
                    agent_id=agent_id,
                    memory_type=memory_type,
                    priority=priority,
                    version=version,
                    timestamp=upload_result.upload_time,
                    size=upload_result.size,
                    tags=tags,
                    parent_cid=parent_cid,
                    expires_at=expires_at,
                )

                # Store record
                self.memory_records[upload_result.cid] = memory_record

                # Update agent index
                if agent_id not in self.agent_memories:
                    self.agent_memories[agent_id] = []
                self.agent_memories[agent_id].append(upload_result.cid)

                # Limit memories per agent
                await self._enforce_memory_limit(agent_id)

                # Save to database
                await self._save_memory_record(memory_record)

                logger.info(f"Stored memory for agent {agent_id}: CID {upload_result.cid}")
                return upload_result

            except Exception as e:
                logger.error(f"Failed to store memory for agent {agent_id}: {e}")
                raise

    async def retrieve_memory(self, cid: str, update_access: bool = True) -> tuple[Any, MemoryRecord]:
        """Retrieve memory data and metadata"""

        async with self._lock:
            try:
                # Get memory record
                memory_record = self.memory_records.get(cid)
                if not memory_record:
                    raise ValueError(f"Memory record not found for CID: {cid}")

                # Check expiration
                if memory_record.expires_at and memory_record.expires_at < datetime.utcnow():
                    raise ValueError(f"Memory has expired: {cid}")

                # Retrieve from IPFS
                memory_data, metadata = await self.ipfs_service.retrieve_memory(cid)

                # Update access count
                if update_access:
                    await self._update_access_count(cid)

                return memory_data, memory_record

            except Exception as e:
                logger.error(f"Failed to retrieve memory {cid}: {e}")
                raise

    async def batch_store_memories(
        self,
        agent_id: str,
        memories: list[tuple[Any, MemoryType, MemoryPriority, list[str]]],
        batch_size: int | None = None,
    ) -> list[IPFSUploadResult]:
        """Store multiple memories in batches"""

        batch_size = batch_size or self.config.batch_upload_size
        results = []

        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]

            # Process batch
            batch_tasks = []
            for memory_data, memory_type, priority, tags in batch:
                task = self.store_memory(
                    agent_id=agent_id, memory_data=memory_data, memory_type=memory_type, priority=priority, tags=tags
                )
                batch_tasks.append(task)

            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"Batch store failed: {result}")
                    else:
                        results.append(result)

            except Exception as e:
                logger.error(f"Batch store error: {e}")

        return results

    async def list_agent_memories(
        self,
        agent_id: str,
        memory_type: MemoryType | None = None,
        limit: int = 100,
        sort_by: str = "timestamp",
        ascending: bool = False,
    ) -> list[MemoryRecord]:
        """List memories for an agent with filtering and sorting"""

        async with self._lock:
            try:
                agent_cids = self.agent_memories.get(agent_id, [])
                memories = []

                for cid in agent_cids:
                    memory_record = self.memory_records.get(cid)
                    if memory_record:
                        # Filter by memory type
                        if memory_type and memory_record.memory_type != memory_type:
                            continue

                        # Filter expired memories
                        if memory_record.expires_at and memory_record.expires_at < datetime.utcnow():
                            continue

                        memories.append(memory_record)

                # Sort
                if sort_by == "timestamp":
                    memories.sort(key=lambda x: x.timestamp, reverse=not ascending)
                elif sort_by == "access_count":
                    memories.sort(key=lambda x: x.access_count, reverse=not ascending)
                elif sort_by == "size":
                    memories.sort(key=lambda x: x.size, reverse=not ascending)

                return memories[:limit]

            except Exception as e:
                logger.error(f"Failed to list memories for agent {agent_id}: {e}")
                return []

    async def delete_memory(self, cid: str, permanent: bool = False) -> bool:
        """Delete memory (unpin or permanent deletion)"""

        async with self._lock:
            try:
                memory_record = self.memory_records.get(cid)
                if not memory_record:
                    return False

                # Don't delete critical memories unless permanent
                if memory_record.priority == MemoryPriority.CRITICAL and not permanent:
                    logger.warning(f"Cannot delete critical memory: {cid}")
                    return False

                # Unpin from IPFS
                if permanent:
                    await self.ipfs_service.delete_memory(cid)

                # Remove from records
                del self.memory_records[cid]

                # Update agent index
                if memory_record.agent_id in self.agent_memories:
                    self.agent_memories[memory_record.agent_id].remove(cid)

                # Delete from database
                await self._delete_memory_record(cid)

                logger.info(f"Deleted memory: {cid}")
                return True

            except Exception as e:
                logger.error(f"Failed to delete memory {cid}: {e}")
                return False

    async def get_memory_statistics(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get memory statistics"""

        async with self._lock:
            try:
                if agent_id:
                    # Statistics for specific agent
                    agent_cids = self.agent_memories.get(agent_id, [])
                    memories = [self.memory_records[cid] for cid in agent_cids if cid in self.memory_records]
                else:
                    # Global statistics
                    memories = list(self.memory_records.values())

                # Calculate statistics
                total_memories = len(memories)
                total_size = sum(m.size for m in memories)

                # By type
                by_type = {}
                for memory in memories:
                    memory_type = memory.memory_type.value
                    by_type[memory_type] = by_type.get(memory_type, 0) + 1

                # By priority
                by_priority = {}
                for memory in memories:
                    priority = memory.priority.value
                    by_priority[priority] = by_priority.get(priority, 0) + 1

                # Access statistics
                total_access = sum(m.access_count for m in memories)
                avg_access = total_access / total_memories if total_memories > 0 else 0

                return {
                    "total_memories": total_memories,
                    "total_size_bytes": total_size,
                    "total_size_mb": total_size / (1024 * 1024),
                    "by_type": by_type,
                    "by_priority": by_priority,
                    "total_access_count": total_access,
                    "average_access_count": avg_access,
                    "agent_count": len(self.agent_memories) if not agent_id else 1,
                }

            except Exception as e:
                logger.error(f"Failed to get memory statistics: {e}")
                return {}

    async def optimize_storage(self) -> dict[str, Any]:
        """Optimize storage by archiving old memories and deduplication"""

        async with self._lock:
            try:
                optimization_results = {"archived": 0, "deduplicated": 0, "compressed": 0, "errors": []}

                # Archive old low-priority memories
                cutoff_date = datetime.utcnow() - timedelta(days=self.config.auto_cleanup_days)

                for cid, memory_record in list(self.memory_records.items()):
                    if (
                        memory_record.priority in [MemoryPriority.LOW, MemoryPriority.TEMPORARY]
                        and memory_record.timestamp < cutoff_date
                    ):

                        try:
                            # Create Filecoin deal for persistence
                            deal_id = await self.ipfs_service.create_filecoin_deal(cid)
                            if deal_id:
                                optimization_results["archived"] += 1
                        except Exception as e:
                            optimization_results["errors"].append(f"Archive failed for {cid}: {e}")

                return optimization_results

            except Exception as e:
                logger.error(f"Storage optimization failed: {e}")
                return {"error": str(e)}

    async def _find_duplicate_memory(self, agent_id: str, memory_data: Any) -> str | None:
        """Find duplicate memory using content hash"""
        # Simplified duplicate detection
        # In real implementation, this would use content-based hashing
        return None

    async def _get_next_version(self, agent_id: str, memory_type: MemoryType, parent_cid: str | None) -> int:
        """Get next version number for memory"""

        # Find existing versions of this memory type
        max_version = 0
        for cid in self.agent_memories.get(agent_id, []):
            memory_record = self.memory_records.get(cid)
            if memory_record and memory_record.memory_type == memory_type and memory_record.parent_cid == parent_cid:
                max_version = max(max_version, memory_record.version)

        return max_version + 1

    async def _update_access_count(self, cid: str):
        """Update access count and last accessed time"""
        memory_record = self.memory_records.get(cid)
        if memory_record:
            memory_record.access_count += 1
            memory_record.last_accessed = datetime.utcnow()
            await self._save_memory_record(memory_record)

    async def _enforce_memory_limit(self, agent_id: str):
        """Enforce maximum memories per agent"""

        agent_cids = self.agent_memories.get(agent_id, [])
        if len(agent_cids) <= self.config.max_memories_per_agent:
            return

        # Sort by priority and access count (keep important memories)
        memories = [(self.memory_records[cid], cid) for cid in agent_cids if cid in self.memory_records]

        # Sort by priority (critical first) and access count
        priority_order = {
            MemoryPriority.CRITICAL: 0,
            MemoryPriority.HIGH: 1,
            MemoryPriority.MEDIUM: 2,
            MemoryPriority.LOW: 3,
            MemoryPriority.TEMPORARY: 4,
        }

        memories.sort(key=lambda x: (priority_order.get(x[0].priority, 5), -x[0].access_count, x[0].timestamp))

        # Delete excess memories (keep the most important)
        excess_count = len(memories) - self.config.max_memories_per_agent
        for i in range(excess_count):
            memory_record, cid = memories[-(i + 1)]  # Delete least important
            await self.delete_memory(cid, permanent=False)

    async def _cleanup_expired_memories(self):
        """Background task to clean up expired memories"""

        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                current_time = datetime.utcnow()
                expired_cids = []

                for cid, memory_record in self.memory_records.items():
                    if (
                        memory_record.expires_at
                        and memory_record.expires_at < current_time
                        and memory_record.priority != MemoryPriority.CRITICAL
                    ):
                        expired_cids.append(cid)

                # Delete expired memories
                for cid in expired_cids:
                    await self.delete_memory(cid, permanent=True)

                if expired_cids:
                    logger.info(f"Cleaned up {len(expired_cids)} expired memories")

            except Exception as e:
                logger.error(f"Memory cleanup error: {e}")

    async def _load_memory_records(self):
        """Load memory records from database"""
        # In real implementation, this would load from database
        pass

    async def _save_memory_record(self, memory_record: MemoryRecord):
        """Save memory record to database"""
        # In real implementation, this would save to database
        pass

    async def _delete_memory_record(self, cid: str):
        """Delete memory record from database"""
        # In real implementation, this would delete from database
        pass

    async def _get_upload_result(self, cid: str) -> IPFSUploadResult:
        """Get upload result for existing CID"""
        # In real implementation, this would retrieve from database
        return IPFSUploadResult(cid=cid, size=0, compressed_size=0, upload_time=datetime.utcnow())
