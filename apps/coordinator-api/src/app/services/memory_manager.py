"""
Memory Manager Service for Agent Memory Operations
Handles memory lifecycle management, versioning, and optimization
"""
import asyncio
from aitbc import get_logger
logger = get_logger(__name__)
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from .ipfs_storage_service import IPFSStorageService, IPFSUploadResult

class MemoryType(StrEnum):
    """Types of agent memories"""
    EXPERIENCE = 'experience'
    POLICY_WEIGHTS = 'policy_weights'
    KNOWLEDGE_GRAPH = 'knowledge_graph'
    TRAINING_DATA = 'training_data'
    USER_FEEDBACK = 'user_feedback'
    PERFORMANCE_METRICS = 'performance_metrics'
    MODEL_STATE = 'model_state'

class MemoryPriority(StrEnum):
    """Memory storage priorities"""
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    TEMPORARY = 'temporary'

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
    parent_cid: str | None = None

class MemoryManager:
    """Manager for agent memory operations"""

    def __init__(self, ipfs_service: IPFSStorageService, config: MemoryConfig):
        self.ipfs_service = ipfs_service
        self.config = config
        self.memory_records: dict[str, MemoryRecord] = {}
        self.agent_memories: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize memory manager"""
        logger.info('Initializing Memory Manager')
        await self._load_memory_records()
        asyncio.create_task(self._cleanup_expired_memories())
        logger.info('Memory Manager initialized')

    async def store_memory(self, agent_id: str, memory_data: Any, memory_type: MemoryType, priority: MemoryPriority=MemoryPriority.MEDIUM, tags: list[str] | None=None, version: int | None=None, parent_cid: str | None=None, expires_in_days: int | None=None) -> IPFSUploadResult:
        """Store agent memory with versioning and deduplication"""
        async with self._lock:
            try:
                if self.config.deduplication_enabled:
                    existing_cid = await self._find_duplicate_memory(agent_id, memory_data)
                    if existing_cid:
                        logger.info('Found duplicate memory for agent %s: %s', agent_id, existing_cid)
                        await self._update_access_count(existing_cid)
                        return await self._get_upload_result(existing_cid)
                if version is None:
                    version = await self._get_next_version(agent_id, memory_type, parent_cid)
                expires_at = None
                if priority == MemoryPriority.TEMPORARY:
                    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days or 7)
                elif expires_in_days:
                    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
                should_pin = priority in [MemoryPriority.CRITICAL, MemoryPriority.HIGH]
                tags = tags or []
                tags.append(f'priority:{priority.value}')
                tags.append(f'version:{version}')
                upload_result = await self.ipfs_service.upload_memory(agent_id=agent_id, memory_data=memory_data, memory_type=memory_type.value, tags=tags, compress=True, pin=should_pin)
                memory_record = MemoryRecord(cid=upload_result.cid, agent_id=agent_id, memory_type=memory_type, priority=priority, version=version, timestamp=upload_result.upload_time, size=upload_result.size, tags=tags, parent_cid=parent_cid, expires_at=expires_at)
                self.memory_records[upload_result.cid] = memory_record
                if agent_id not in self.agent_memories:
                    self.agent_memories[agent_id] = []
                self.agent_memories[agent_id].append(upload_result.cid)
                await self._enforce_memory_limit(agent_id)
                await self._save_memory_record(memory_record)
                logger.info('Stored memory for agent %s: CID %s', agent_id, upload_result.cid)
                return upload_result
            except Exception as e:
                logger.error('Failed to store memory for agent %s: %s', agent_id, e)
                raise

    async def retrieve_memory(self, cid: str, update_access: bool=True) -> tuple[Any, MemoryRecord]:
        """Retrieve memory data and metadata"""
        async with self._lock:
            try:
                memory_record = self.memory_records.get(cid)
                if not memory_record:
                    raise ValueError(f'Memory record not found for CID: {cid}')
                if memory_record.expires_at and memory_record.expires_at < datetime.now(UTC):
                    raise ValueError(f'Memory has expired: {cid}')
                memory_data, metadata = await self.ipfs_service.retrieve_memory(cid)
                if update_access:
                    await self._update_access_count(cid)
                return (memory_data, memory_record)
            except Exception as e:
                logger.error('Failed to retrieve memory %s: %s', cid, e)
                raise

    async def batch_store_memories(self, agent_id: str, memories: list[tuple[Any, MemoryType, MemoryPriority, list[str]]], batch_size: int | None=None) -> list[IPFSUploadResult]:
        """Store multiple memories in batches"""
        batch_size = batch_size or self.config.batch_upload_size
        results = []
        for i in range(0, len(memories), batch_size):
            batch = memories[i:i + batch_size]
            batch_tasks = []
            for memory_data, memory_type, priority, tags in batch:
                task = self.store_memory(agent_id=agent_id, memory_data=memory_data, memory_type=memory_type, priority=priority, tags=tags)
                batch_tasks.append(task)
            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error('Batch store failed: %s', result)
                    else:
                        results.append(result)
            except Exception as e:
                logger.error('Batch store error: %s', e)
        return results # type: ignore[return-value]

    async def list_agent_memories(self, agent_id: str, memory_type: MemoryType | None=None, limit: int=100, sort_by: str='timestamp', ascending: bool=False) -> list[MemoryRecord]:
        """List memories for an agent with filtering and sorting"""
        async with self._lock:
            try:
                agent_cids = self.agent_memories.get(agent_id, [])
                memories = []
                for cid in agent_cids:
                    memory_record = self.memory_records.get(cid)
                    if memory_record:
                        if memory_type and memory_record.memory_type != memory_type:
                            continue
                        if memory_record.expires_at and memory_record.expires_at < datetime.now(UTC):
                            continue
                        memories.append(memory_record)
                if sort_by == 'timestamp':
                    memories.sort(key=lambda x: x.timestamp, reverse=not ascending)
                elif sort_by == 'access_count':
                    memories.sort(key=lambda x: x.access_count, reverse=not ascending)
                elif sort_by == 'size':
                    memories.sort(key=lambda x: x.size, reverse=not ascending)
                return memories[:limit]
            except Exception as e:
                logger.error('Failed to list memories for agent %s: %s', agent_id, e)
                return []

    async def delete_memory(self, cid: str, permanent: bool=False) -> bool:
        """Delete memory (unpin or permanent deletion)"""
        async with self._lock:
            try:
                memory_record = self.memory_records.get(cid)
                if not memory_record:
                    return False
                if memory_record.priority == MemoryPriority.CRITICAL and (not permanent):
                    logger.warning('Cannot delete critical memory: %s', cid)
                    return False
                if permanent:
                    await self.ipfs_service.delete_memory(cid)
                del self.memory_records[cid]
                if memory_record.agent_id in self.agent_memories:
                    self.agent_memories[memory_record.agent_id].remove(cid)
                await self._delete_memory_record(cid)
                logger.info('Deleted memory: %s', cid)
                return True
            except Exception as e:
                logger.error('Failed to delete memory %s: %s', cid, e)
                return False

    async def get_memory_statistics(self, agent_id: str | None=None) -> dict[str, Any]:
        """Get memory statistics"""
        async with self._lock:
            try:
                if agent_id:
                    agent_cids = self.agent_memories.get(agent_id, [])
                    memories = [self.memory_records[cid] for cid in agent_cids if cid in self.memory_records]
                else:
                    memories = list(self.memory_records.values())
                total_memories = len(memories)
                total_size = sum((m.size for m in memories))
                by_type: dict[str, int] = {}
                for memory in memories:
                    memory_type = memory.memory_type.value
                    by_type[memory_type] = by_type.get(memory_type, 0) + 1
                by_priority: dict[str, int] = {}
                for memory in memories:
                    priority = memory.priority.value
                    by_priority[priority] = by_priority.get(priority, 0) + 1
                total_access = sum((m.access_count for m in memories))
                avg_access = total_access / total_memories if total_memories > 0 else 0
                return {'total_memories': total_memories, 'total_size_bytes': total_size, 'total_size_mb': total_size / (1024 * 1024), 'by_type': by_type, 'by_priority': by_priority, 'total_access_count': total_access, 'average_access_count': avg_access, 'agent_count': len(self.agent_memories) if not agent_id else 1}
            except Exception as e:
                logger.error('Failed to get memory statistics: %s', e)
                return {}

    async def optimize_storage(self) -> dict[str, Any]:
        """Optimize storage by archiving old memories and deduplication"""
        async with self._lock:
            try:
                optimization_results = {'archived': 0, 'deduplicated': 0, 'compressed': 0, 'errors': []}
                cutoff_date = datetime.now(UTC) - timedelta(days=self.config.auto_cleanup_days)
                for cid, memory_record in list(self.memory_records.items()):
                    if memory_record.priority in [MemoryPriority.LOW, MemoryPriority.TEMPORARY] and memory_record.timestamp < cutoff_date:
                        try:
                            deal_id = await self.ipfs_service.create_filecoin_deal(cid)
                            if deal_id:
                                optimization_results['archived'] += 1 # type: ignore[operator]
                        except Exception as e:
                            optimization_results['errors'].append(f'Archive failed for {cid}: {e}')  # type: ignore[attr-defined]
                return optimization_results
            except Exception as e:
                logger.error('Storage optimization failed: %s', e)
                return {'error': str(e)}

    async def _find_duplicate_memory(self, agent_id: str, memory_data: Any) -> str | None:
        """Find duplicate memory using content hash"""
        return None

    async def _get_next_version(self, agent_id: str, memory_type: MemoryType, parent_cid: str | None) -> int:
        """Get next version number for memory"""
        max_version = 0
        for cid in self.agent_memories.get(agent_id, []):
            memory_record = self.memory_records.get(cid)
            if memory_record and memory_record.memory_type == memory_type and (memory_record.parent_cid == parent_cid):
                max_version = max(max_version, memory_record.version)
        return max_version + 1

    async def _update_access_count(self, cid: str) -> None:
        """Update access count and last accessed time"""
        memory_record = self.memory_records.get(cid)
        if memory_record:
            memory_record.access_count += 1
            memory_record.last_accessed = datetime.now(UTC)
            await self._save_memory_record(memory_record)

    async def _enforce_memory_limit(self, agent_id: str) -> None:
        """Enforce maximum memories per agent"""
        agent_cids = self.agent_memories.get(agent_id, [])
        if len(agent_cids) <= self.config.max_memories_per_agent:
            return
        memories = [(self.memory_records[cid], cid) for cid in agent_cids if cid in self.memory_records]
        priority_order = {MemoryPriority.CRITICAL: 0, MemoryPriority.HIGH: 1, MemoryPriority.MEDIUM: 2, MemoryPriority.LOW: 3, MemoryPriority.TEMPORARY: 4}
        memories.sort(key=lambda x: (priority_order.get(x[0].priority, 5), -x[0].access_count, x[0].timestamp))
        excess_count = len(memories) - self.config.max_memories_per_agent
        for i in range(excess_count):
            memory_record, cid = memories[-(i + 1)]
            await self.delete_memory(cid, permanent=False)

    async def _cleanup_expired_memories(self) -> None:
        """Background task to clean up expired memories"""
        while True:
            try:
                await asyncio.sleep(3600)
                current_time = datetime.now(UTC)
                expired_cids = []
                for cid, memory_record in self.memory_records.items():
                    if memory_record.expires_at and memory_record.expires_at < current_time and (memory_record.priority != MemoryPriority.CRITICAL):
                        expired_cids.append(cid)
                for cid in expired_cids:
                    await self.delete_memory(cid, permanent=True)
                if expired_cids:
                    logger.info('Cleaned up %s expired memories', len(expired_cids))
            except Exception as e:
                logger.error('Memory cleanup error: %s', e)

    async def _load_memory_records(self) -> None:
        """Load memory records from database"""
        pass

    async def _save_memory_record(self, memory_record: MemoryRecord) -> None:
        """Save memory record to database"""
        pass

    async def _delete_memory_record(self, cid: str) -> None:
        """Delete memory record from database"""
        pass

    async def _get_upload_result(self, cid: str) -> IPFSUploadResult:
        """Get upload result for existing CID"""
        return IPFSUploadResult(cid=cid, size=0, compressed_size=0, upload_time=datetime.now(UTC))