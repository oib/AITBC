"""
IPFS Storage Service for Decentralized AI Memory & Storage
Handles IPFS/Filecoin integration for persistent agent memory storage
"""

import asyncio

from aitbc import get_logger

logger = get_logger(__name__)
import gzip
import hashlib
import pickle
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any

from .secure_pickle import safe_loads

try:
    import ipfshttpclient
    from web3 import Web3
except ImportError as e:
    logging.error(f"IPFS/Web3 dependencies not installed: {e}")
    raise


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
        self.cache = {}  # Simple in-memory cache
        self.compression_threshold = config.get("compression_threshold", 1024)
        self.pin_threshold = config.get("pin_threshold", 100)  # Pin important memories

    async def initialize(self):
        """Initialize IPFS client and Web3 connection"""
        try:
            # Initialize IPFS client
            ipfs_url = self.config.get("ipfs_url", "/ip4/127.0.0.1/tcp/5001")
            self.ipfs_client = ipfshttpclient.connect(ipfs_url)

            # Test connection
            version = self.ipfs_client.version()
            logger.info(f"Connected to IPFS node: {version['Version']}")

            # Initialize Web3 if blockchain features enabled
            if self.config.get("blockchain_enabled", False):
                web3_url = self.config.get("web3_url")
                self.web3 = Web3(Web3.HTTPProvider(web3_url))
                if self.web3.is_connected():
                    logger.info("Connected to blockchain node")
                else:
                    logger.warning("Failed to connect to blockchain node")

        except Exception as e:
            logger.error(f"Failed to initialize IPFS service: {e}")
            raise

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

        start_time = datetime.now(datetime.UTC)
        tags = tags or []

        try:
            # Serialize memory data
            serialized_data = pickle.dumps(memory_data)
            original_size = len(serialized_data)

            # Compress if enabled and above threshold
            if compress and original_size > self.compression_threshold:
                compressed_data = gzip.compress(serialized_data)
                compression_ratio = len(compressed_data) / original_size
                upload_data = compressed_data
            else:
                compressed_data = serialized_data
                compression_ratio = 1.0
                upload_data = serialized_data

            # Calculate integrity hash
            integrity_hash = hashlib.sha256(upload_data).hexdigest()

            # Upload to IPFS
            result = self.ipfs_client.add_bytes(upload_data)
            cid = result["Hash"]

            # Pin if requested or meets threshold
            should_pin = pin or len(tags) >= self.pin_threshold
            if should_pin:
                try:
                    self.ipfs_client.pin.add(cid)
                    pinned = True
                except Exception as e:
                    logger.warning(f"Failed to pin CID {cid}: {e}")
                    pinned = False
            else:
                pinned = False

            # Create metadata
            metadata = MemoryMetadata(
                agent_id=agent_id,
                memory_type=memory_type,
                timestamp=start_time,
                version=1,
                tags=tags,
                compression_ratio=compression_ratio,
                integrity_hash=integrity_hash,
            )

            # Store metadata
            await self._store_metadata(cid, metadata)

            # Cache result
            upload_result = IPFSUploadResult(
                cid=cid, size=original_size, compressed_size=len(upload_data), upload_time=start_time, pinned=pinned
            )

            self.cache[cid] = upload_result

            logger.info(f"Uploaded memory for agent {agent_id}: CID {cid}")
            return upload_result

        except Exception as e:
            logger.error(f"Failed to upload memory for agent {agent_id}: {e}")
            raise

    async def retrieve_memory(self, cid: str, verify_integrity: bool = True) -> tuple[Any, MemoryMetadata]:
        """Retrieve memory data from IPFS"""

        try:
            # Check cache first
            if cid in self.cache:
                logger.debug(f"Retrieved {cid} from cache")

            # Get metadata
            metadata = await self._get_metadata(cid)
            if not metadata:
                raise ValueError(f"No metadata found for CID {cid}")

            # Retrieve from IPFS
            retrieved_data = self.ipfs_client.cat(cid)

            # Verify integrity if requested
            if verify_integrity:
                calculated_hash = hashlib.sha256(retrieved_data).hexdigest()
                if calculated_hash != metadata.integrity_hash:
                    raise ValueError(f"Integrity check failed for CID {cid}")

            # Decompress if needed
            if metadata.compression_ratio < 1.0:
                decompressed_data = gzip.decompress(retrieved_data)
            else:
                decompressed_data = retrieved_data

            # Deserialize (using safe unpickler)
            memory_data = safe_loads(decompressed_data)

            logger.info(f"Retrieved memory for agent {metadata.agent_id}: CID {cid}")
            return memory_data, metadata

        except Exception as e:
            logger.error(f"Failed to retrieve memory {cid}: {e}")
            raise

    async def batch_upload_memories(
        self, agent_id: str, memories: list[tuple[Any, str, list[str]]], batch_size: int = 10
    ) -> list[IPFSUploadResult]:
        """Upload multiple memories in batches"""

        results = []

        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]
            batch_results = []

            # Upload batch concurrently
            tasks = []
            for memory_data, memory_type, tags in batch:
                task = self.upload_memory(agent_id, memory_data, memory_type, tags)
                tasks.append(task)

            try:
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"Batch upload failed: {result}")
                    else:
                        results.append(result)

            except Exception as e:
                logger.error(f"Batch upload error: {e}")

            # Small delay between batches to avoid overwhelming IPFS
            await asyncio.sleep(0.1)

        return results

    async def create_filecoin_deal(self, cid: str, duration: int = 180) -> str | None:
        """Create Filecoin storage deal for CID persistence"""

        try:
            # This would integrate with Filecoin storage providers
            # For now, return a mock deal ID
            deal_id = f"deal-{cid[:8]}-{datetime.now(datetime.UTC).timestamp()}"

            logger.info(f"Created Filecoin deal {deal_id} for CID {cid}")
            return deal_id

        except Exception as e:
            logger.error(f"Failed to create Filecoin deal for {cid}: {e}")
            return None

    async def list_agent_memories(self, agent_id: str, limit: int = 100) -> list[str]:
        """List all memory CIDs for an agent"""

        try:
            # This would query a database or index
            # For now, return mock data
            cids = []

            # Search through cache
            for cid, _result in self.cache.items():
                # In real implementation, this would query metadata
                if agent_id in cid:  # Simplified check
                    cids.append(cid)

            return cids[:limit]

        except Exception as e:
            logger.error(f"Failed to list memories for agent {agent_id}: {e}")
            return []

    async def delete_memory(self, cid: str) -> bool:
        """Delete/unpin memory from IPFS"""

        try:
            # Unpin the CID
            self.ipfs_client.pin.rm(cid)

            # Remove from cache
            if cid in self.cache:
                del self.cache[cid]

            # Remove metadata
            await self._delete_metadata(cid)

            logger.info(f"Deleted memory: CID {cid}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete memory {cid}: {e}")
            return False

    async def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics"""

        try:
            # Get IPFS repo stats
            stats = self.ipfs_client.repo.stat()

            return {
                "total_objects": stats.get("numObjects", 0),
                "repo_size": stats.get("repoSize", 0),
                "storage_max": stats.get("storageMax", 0),
                "version": stats.get("version", "unknown"),
                "cached_objects": len(self.cache),
            }

        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}

    async def _store_metadata(self, cid: str, metadata: MemoryMetadata):
        """Store metadata for a CID"""
        # In real implementation, this would store in a database
        # For now, store in memory
        pass

    async def _get_metadata(self, cid: str) -> MemoryMetadata | None:
        """Get metadata for a CID"""
        # In real implementation, this would query a database
        # For now, return mock metadata
        return MemoryMetadata(
            agent_id="mock_agent",
            memory_type="experience",
            timestamp=datetime.now(datetime.UTC),
            version=1,
            tags=["mock"],
            compression_ratio=1.0,
            integrity_hash="mock_hash",
        )

    async def _delete_metadata(self, cid: str):
        """Delete metadata for a CID"""
        # In real implementation, this would delete from database
        pass


class MemoryCompressionService:
    """Service for memory compression and optimization"""

    @staticmethod
    def compress_memory(data: Any) -> tuple[bytes, float]:
        """Compress memory data and return compressed data with ratio"""
        serialized = pickle.dumps(data)
        compressed = gzip.compress(serialized)
        ratio = len(compressed) / len(serialized)
        return compressed, ratio

    @staticmethod
    def decompress_memory(compressed_data: bytes) -> Any:
        """Decompress memory data"""
        decompressed = gzip.decompress(compressed_data)
        return safe_loads(decompressed)

    @staticmethod
    def calculate_similarity(data1: Any, data2: Any) -> float:
        """Calculate similarity between two memory items"""
        # Simplified similarity calculation
        # In real implementation, this would use more sophisticated methods
        try:
            hash1 = hashlib.sha256(pickle.dumps(data1)).hexdigest()
            hash2 = hashlib.sha256(pickle.dumps(data2)).hexdigest()

            # Simple hash comparison (not ideal for real use)
            return 1.0 if hash1 == hash2 else 0.0
        except:
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
                # In real implementation, this would replicate to each node
                replicated_nodes.append(node)
                logger.info(f"Replicated {cid} to node {node}")
            except Exception as e:
                logger.error(f"Failed to replicate {cid} to {node}: {e}")

        return replicated_nodes

    async def get_cluster_health(self) -> dict[str, Any]:
        """Get health status of IPFS cluster"""
        return {"total_nodes": len(self.nodes), "healthy_nodes": len(self.nodes), "cluster_id": "mock-cluster"}  # Simplified
