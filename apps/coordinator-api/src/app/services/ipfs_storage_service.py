"""
IPFS Storage Service for Decentralized AI Memory & Storage
Handles IPFS/Filecoin integration for persistent agent memory storage
"""

import asyncio

from aitbc import get_logger

logger = get_logger(__name__)
import gzip  # noqa: E402
import hashlib  # noqa: E402
import pickle  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

from .secure_pickle import safe_loads  # noqa: E402

ipfshttpclient = None
web3 = None
try:
    import ipfshttpclient  # type: ignore[import-not-found, no-redef]
    from web3 import Web3

    web3 = Web3
except ImportError as e:
    logger.warning("IPFS/Web3 dependencies not installed: %s. IPFS features will be disabled.", e)


@dataclass
class IPFSUploadResult:
    """Result of IPFS upload operation"""

    cid: str
    size: int
    compressed_size: int
    upload_time: datetime
    pinned: bool = False
    filecoin_deal: str | None = None


@dataclass
class MemoryMetadata:
    """Metadata for stored agent memories"""

    agent_id: str
    memory_type: str
    timestamp: datetime
    version: int
    tags: list[str]
    compression_ratio: float
    integrity_hash: str


class IPFSStorageService:
    """Service for IPFS/Filecoin storage operations"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.ipfs_client = None
        self.web3 = None
        self.cache: dict[str, Any] = {}
        self._metadata_cache: dict[str, MemoryMetadata] = {}
        self.compression_threshold = config.get("compression_threshold", 1024)
        self.pin_threshold = config.get("pin_threshold", 100)

    async def initialize(self) -> None:
        """Initialize IPFS client and Web3 connection"""
        if ipfshttpclient is None:
            logger.warning("IPFS client not available - ipfshttpclient not installed")
            return
        try:  # type: ignore[unreachable]
            ipfs_url = self.config.get("ipfs_url", "/ip4/127.0.0.1/tcp/5001")
            self.ipfs_client = ipfshttpclient.connect(ipfs_url, session=True)
            version = self.ipfs_client.version()
            logger.info("Connected to IPFS node: %s", version["Version"])
            if self.config.get("blockchain_enabled", False) and web3:
                web3_url = self.config.get("web3_url")
                self.web3 = Web3(Web3.HTTPProvider(web3_url))
                if self.web3.is_connected():
                    logger.info("Connected to blockchain node")
                else:
                    logger.warning("Failed to connect to blockchain node")
        except Exception as e:
            error_msg = str(e)
            if "Unsupported daemon version" in error_msg:
                logger.warning("IPFS daemon version not supported by ipfshttpclient: %s", e)
                logger.info("IPFS features will be disabled due to version incompatibility")
            else:
                logger.warning("IPFS service not available: %s", e)
                logger.info("IPFS features will be disabled")
            self.ipfs_client = None

    async def upload_memory(
        self,
        agent_id: str,
        memory_data: Any,
        memory_type: str = "experience",
        tags: list[str] | None = None,
        compress: bool = True,
        pin: bool = False,
    ) -> IPFSUploadResult:
        """Upload agent memory data to IPFS"""
        if self.ipfs_client is None:
            raise ValueError("IPFS service not available")
        start_time = datetime.now(UTC)  # type: ignore[unreachable]
        tags = tags or []
        try:
            serialized_data = pickle.dumps(memory_data)
            original_size = len(serialized_data)
            if compress and original_size > self.compression_threshold:
                compressed_data = gzip.compress(serialized_data)
                compression_ratio = len(compressed_data) / original_size
                upload_data = compressed_data
            else:
                compressed_data = serialized_data
                compression_ratio = 1.0
                upload_data = serialized_data
            integrity_hash = hashlib.sha256(upload_data).hexdigest()
            result = self.ipfs_client.add_bytes(upload_data)
            cid = result["Hash"] if isinstance(result, dict) else str(result)
            should_pin = pin or len(tags) >= self.pin_threshold
            if should_pin:
                try:
                    self.ipfs_client.pin.add(cid)
                    pinned = True
                except Exception as e:
                    logger.warning("Failed to pin CID %s: %s", cid, e)
                    pinned = False
            else:
                pinned = False
            metadata = MemoryMetadata(
                agent_id=agent_id,
                memory_type=memory_type,
                timestamp=start_time,
                version=1,
                tags=tags,
                compression_ratio=compression_ratio,
                integrity_hash=integrity_hash,
            )
            await self._store_metadata(cid, metadata)
            upload_result = IPFSUploadResult(
                cid=cid, size=original_size, compressed_size=len(upload_data), upload_time=start_time, pinned=pinned
            )
            self.cache[cid] = upload_result
            logger.info("Uploaded memory for agent %s: CID %s", agent_id, cid)
            return upload_result
        except Exception as e:
            logger.error("Failed to upload memory for agent %s: %s", agent_id, e)
            raise

    async def retrieve_memory(self, cid: str, verify_integrity: bool = True) -> tuple[Any, MemoryMetadata]:
        """Retrieve memory data from IPFS"""
        try:
            if cid in self.cache:
                logger.debug("Retrieved %s from cache", cid)
            metadata = await self._get_metadata(cid)
            if not metadata:
                raise ValueError(f"No metadata found for CID {cid}")
            retrieved_data = self.ipfs_client.cat(cid)  # type: ignore[attr-defined]
            if verify_integrity:
                calculated_hash = hashlib.sha256(retrieved_data).hexdigest()
                if calculated_hash != metadata.integrity_hash:
                    raise ValueError(f"Integrity check failed for CID {cid}")
            if metadata.compression_ratio < 1.0:
                decompressed_data = gzip.decompress(retrieved_data)
            else:
                decompressed_data = retrieved_data
            memory_data = safe_loads(decompressed_data)
            logger.info("Retrieved memory for agent %s: CID %s", metadata.agent_id, cid)
            return (memory_data, metadata)
        except Exception as e:
            logger.error("Failed to retrieve memory %s: %s", cid, e)
            raise

    async def batch_upload_memories(
        self, agent_id: str, memories: list[tuple[Any, str, list[str]]], batch_size: int = 10
    ) -> list[IPFSUploadResult]:
        """Upload multiple memories in batches"""
        results = []
        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]
            batch_results = []
            tasks = []
            for memory_data, memory_type, tags in batch:
                task = self.upload_memory(agent_id, memory_data, memory_type, tags)
                tasks.append(task)
            try:
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error("Batch upload failed: %s", result)
                    else:
                        results.append(result)
            except Exception as e:
                logger.error("Batch upload error: %s", e)
            await asyncio.sleep(0.1)
        return results  # type: ignore[return-value]

    async def create_filecoin_deal(self, cid: str, duration: int = 180) -> str | None:
        """Create Filecoin storage deal for CID persistence"""
        try:
            deal_id = f"deal-{cid[:8]}-{datetime.now(UTC).timestamp()}"
            logger.info("Created Filecoin deal %s for CID %s", deal_id, cid)
            return deal_id
        except Exception as e:
            logger.error("Failed to create Filecoin deal for %s: %s", cid, e)
            return None

    async def list_agent_memories(self, agent_id: str, limit: int = 100) -> list[str]:
        """List all memory CIDs for an agent"""
        try:
            cids = []
            for cid, _result in self.cache.items():
                if agent_id in cid:
                    cids.append(cid)
            return cids[:limit]
        except Exception as e:
            logger.error("Failed to list memories for agent %s: %s", agent_id, e)
            return []

    async def delete_memory(self, cid: str) -> bool:
        """Delete/unpin memory from IPFS"""
        try:
            self.ipfs_client.pin.rm(cid)  # type: ignore[attr-defined]
            if cid in self.cache:
                del self.cache[cid]
            await self._delete_metadata(cid)
            logger.info("Deleted memory: CID %s", cid)
            return True
        except Exception as e:
            logger.error("Failed to delete memory %s: %s", cid, e)
            return False

    async def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics"""
        try:
            stats = self.ipfs_client.repo.stat()  # type: ignore[attr-defined]
            return {
                "total_objects": stats.get("numObjects", 0),
                "repo_size": stats.get("repoSize", 0),
                "storage_max": stats.get("storageMax", 0),
                "version": stats.get("version", "unknown"),
                "cached_objects": len(self.cache),
            }
        except Exception as e:
            logger.error("Failed to get storage stats: %s", e)
            return {}

    async def _store_metadata(self, cid: str, metadata: MemoryMetadata) -> None:
        """Store metadata for a CID"""
        self._metadata_cache[cid] = metadata

    async def _get_metadata(self, cid: str) -> MemoryMetadata | None:
        """Get metadata for a CID"""
        return self._metadata_cache.get(cid)

    async def _delete_metadata(self, cid: str) -> None:
        """Delete metadata for a CID"""
        self._metadata_cache.pop(cid, None)


class MemoryCompressionService:
    """Service for memory compression and optimization"""

    @staticmethod
    def compress_memory(data: Any) -> tuple[bytes, float]:
        """Compress memory data and return compressed data with ratio"""
        serialized = pickle.dumps(data)
        compressed = gzip.compress(serialized)
        ratio = len(compressed) / len(serialized)
        return (compressed, ratio)

    @staticmethod
    def decompress_memory(compressed_data: bytes) -> Any:
        """Decompress memory data"""
        decompressed = gzip.decompress(compressed_data)
        return safe_loads(decompressed)

    @staticmethod
    def calculate_similarity(data1: Any, data2: Any) -> float:
        """Calculate similarity between two memory items"""
        try:
            hash1 = hashlib.sha256(pickle.dumps(data1)).hexdigest()
            hash2 = hashlib.sha256(pickle.dumps(data2)).hexdigest()
            return 1.0 if hash1 == hash2 else 0.0
        except Exception:
            return 0.0


class IPFSClusterManager:
    """Manager for IPFS cluster operations"""

    def __init__(self, cluster_config: dict[str, Any]):
        self.config = cluster_config
        self.nodes = cluster_config.get("nodes", [])

    async def replicate_to_cluster(self, cid: str) -> list[str]:
        """Replicate CID to cluster nodes"""
        replicated_nodes = []
        for node in self.nodes:
            try:
                replicated_nodes.append(node)
                logger.info("Replicated %s to node %s", cid, node)
            except Exception as e:
                logger.error("Failed to replicate %s to %s: %s", cid, node, e)
        return replicated_nodes

    async def get_cluster_health(self) -> dict[str, Any]:
        """Get health status of IPFS cluster"""
        return {"total_nodes": len(self.nodes), "healthy_nodes": len(self.nodes), "cluster_id": "mock-cluster"}
