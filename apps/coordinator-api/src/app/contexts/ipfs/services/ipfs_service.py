"""
IPFS Service - Real IPFS integration for decentralized storage

Provides:
- File upload to IPFS
- CID generation and retrieval
- Pin management
- Gateway access
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class IPFSUploadResult:
    """Result of IPFS upload"""

    cid: str
    size: int
    name: str
    timestamp: datetime
    gateway_url: str
    pinned: bool


@dataclass
class IPFSPin:
    """IPFS pin record"""

    cid: str
    name: str
    size: int
    pinned_at: datetime
    metadata: dict[str, Any]


class IPFSClient:
    """
    IPFS client for interacting with IPFS nodes.

    Supports:
    - Local IPFS node (default: localhost:5001)
    - Infura IPFS
    - Pinata
    - Other pinning services
    """

    def __init__(
        self,
        api_url: str = "http://localhost:5001",
        gateway_url: str = "https://ipfs.io",
        pinning_service: str | None = None,
        pinning_key: str | None = None,
        session: Any = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.pinning_service = pinning_service
        self.pinning_key = pinning_key
        self._client = httpx.AsyncClient(timeout=60.0)
        self._available: bool | None = None

    async def check_availability(self) -> bool:
        """Check if IPFS node is available"""
        if self._available is not None:
            return self._available
        try:
            response = await self._client.post(f"{self.api_url}/api/v0/id", timeout=5.0)
            self._available = response.status_code == 200
            if self._available:
                data = response.json()
                logger.info("IPFS node connected: %s...", data.get("ID", "unknown")[:16])
            return self._available
        except Exception as e:
            logger.warning("IPFS node not available: %s", e)
            self._available = False
            return False

    async def upload_file(
        self, data: bytes | str, filename: str = "", pin: bool = True, wrap_with_directory: bool = False
    ) -> IPFSUploadResult:
        """
        Upload data to IPFS.

        Args:
            data: File content (bytes or string)
            filename: Optional filename
            pin: Whether to pin the content
            wrap_with_directory: Whether to wrap in a directory

        Returns:
            IPFSUploadResult with CID and metadata
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        is_available = await self.check_availability()
        if is_available:
            return await self._upload_to_ipfs(data, filename, pin, wrap_with_directory)
        else:
            raise RuntimeError(
                "IPFS node is unavailable and no fallback is configured. "
                "Cannot upload data — no real CID can be generated. "
                "Start an IPFS node or configure IPFS_API_URL."
            )

    async def _upload_to_ipfs(self, data: bytes, filename: str, pin: bool, wrap_with_directory: bool) -> IPFSUploadResult:
        """Upload to real IPFS node"""
        try:
            files = {"file": (filename or "data", data)}
            params = {}
            if pin:
                params["pin"] = "true"
            if wrap_with_directory:
                params["wrap-with-directory"] = "true"
            response = await self._client.post(f"{self.api_url}/api/v0/add", files=files, params=params, timeout=60.0)
            response.raise_for_status()
            lines = response.text.strip().split("\n")
            last_line = json.loads(lines[-1])
            cid = last_line.get("Hash")
            size = last_line.get("Size", len(data))
            if pin and self.pinning_service:
                await self._pin_to_external_service(cid, filename, size)
            return IPFSUploadResult(
                cid=cid,
                size=size,
                name=filename or cid[:16],
                timestamp=datetime.now(UTC),
                gateway_url=f"{self.gateway_url}/ipfs/{cid}",
                pinned=pin,
            )
        except Exception as e:
            logger.error("IPFS upload failed: %s", e)
            raise

    async def _pin_to_external_service(self, cid: str, name: str, size: int) -> bool:
        """Pin CID to external pinning service"""
        if not self.pinning_service or not self.pinning_key:
            return False
        try:
            if self.pinning_service == "pinata":
                response = await self._client.post(
                    "https://api.pinata.cloud/pinning/pinByHash",
                    headers={"Authorization": f"Bearer {self.pinning_key}", "Content-Type": "application/json"},
                    json={"hashToPin": cid, "pinataMetadata": {"name": name}},
                    timeout=30.0,
                )
                return response.status_code == 200
            return False
        except Exception as e:
            logger.warning("External pinning failed: %s", e)
            return False

    async def get_content(self, cid: str) -> bytes | None:
        """Retrieve content from IPFS by CID"""
        if cid.startswith("Qm") and len(cid) == 46:
            try:
                response = await self._client.get(f"{self.gateway_url}/ipfs/{cid}", timeout=30.0, follow_redirects=True)
                if response.status_code == 200:
                    return response.content
            except Exception as e:
                logger.debug("Could not fetch from IPFS gateway: %s", e)
        return None

    async def pin_cid(self, cid: str, name: str = "") -> bool:
        """Pin an existing CID to the local node"""
        if not await self.check_availability():
            return False
        try:
            response = await self._client.post(f"{self.api_url}/api/v0/pin/add", params={"arg": cid}, timeout=30.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning("Pin failed: %s", e)
            return False

    async def unpin_cid(self, cid: str) -> bool:
        """Unpin a CID from the local node"""
        if not await self.check_availability():
            return False
        try:
            response = await self._client.post(f"{self.api_url}/api/v0/pin/rm", params={"arg": cid}, timeout=30.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning("Unpin failed: %s", e)
            return False

    async def list_pins(self) -> list[IPFSPin]:
        """List all pinned CIDs"""
        if not await self.check_availability():
            return []
        try:
            response = await self._client.post(f"{self.api_url}/api/v0/pin/ls", timeout=30.0)
            if response.status_code != 200:
                return []
            data = response.json()
            pins = []
            for cid, info in data.get("Keys", {}).items():
                pins.append(
                    IPFSPin(cid=cid, name=info.get("Type", "unknown"), size=0, pinned_at=datetime.now(UTC), metadata=info)
                )
            return pins
        except Exception as e:
            logger.warning("List pins failed: %s", e)
            return []


@dataclass
class MemoryUploadResult:
    """Result of uploading agent memory to IPFS"""

    cid: str
    size: int
    compressed_size: int
    upload_time: datetime
    pinned: bool
    filecoin_deal: str | None = None


@dataclass
class MemoryMetadata:
    """Metadata for a stored memory"""

    agent_id: str
    memory_type: str
    timestamp: datetime
    version: str = "1.0"
    tags: list[str] = None  # type: ignore[assignment]
    compression_ratio: float = 1.0
    integrity_hash: str = ""


class IPFSService:
    """
    High-level IPFS service for the AITBC platform.

    Provides convenient methods for:
    - Storing job results
    - Caching AI model outputs
    - Archiving transaction data
    - Agent memory upload/retrieve/batch/delete
    """

    def __init__(self, session: Any = None) -> None:
        # Accept either a DB session (legacy) or a config dict (router pattern)
        if isinstance(session, dict):
            config = session
            api_url = config.get("ipfs_url", "http://localhost:5001")
            self.client = IPFSClient(api_url=api_url)
        else:
            self.client = IPFSClient()
        self._uploads: dict[str, IPFSUploadResult] = {}
        self._memories: dict[str, tuple[dict[str, Any], MemoryMetadata]] = {}
        self.session = session if not isinstance(session, dict) else None

    async def initialize(self) -> None:
        """Initialize the service — check IPFS node availability."""
        await self.client.check_availability()

    async def store_job_result(self, job_id: str, result_data: dict[str, Any]) -> IPFSUploadResult:
        """Store AI job result on IPFS"""
        data = json.dumps(result_data, indent=2).encode("utf-8")
        result = await self.client.upload_file(data=data, filename=f"job_{job_id}_result.json", pin=True)
        self._uploads[job_id] = result
        logger.info("Job result stored on IPFS: %s -> %s", job_id, result.cid)
        return result

    async def store_evidence(self, dispute_id: str, evidence_data: dict[str, Any]) -> IPFSUploadResult:
        """Store dispute evidence on IPFS"""
        data = json.dumps(evidence_data, indent=2).encode("utf-8")
        result = await self.client.upload_file(data=data, filename=f"dispute_{dispute_id}_evidence.json", pin=True)
        logger.info("Evidence stored on IPFS: %s -> %s", dispute_id, result.cid)
        return result

    async def get_upload(self, job_id: str) -> IPFSUploadResult | None:
        """Get upload result by job ID"""
        return self._uploads.get(job_id)

    async def upload_memory(
        self,
        agent_id: str,
        memory_data: dict[str, Any],
        memory_type: str = "experience",
        tags: list[str] | None = None,
        compress: bool = True,
        pin: bool = False,
    ) -> MemoryUploadResult:
        """Upload agent memory data to IPFS.

        Serializes the memory dict as JSON and uploads it via the IPFS client.
        Raises RuntimeError if IPFS node is unavailable (no mock CIDs).
        """
        tags = tags or []
        raw = json.dumps(memory_data, indent=2).encode("utf-8")
        size = len(raw)
        # Compression is handled by IPFS natively; we track the original size
        result = await self.client.upload_file(
            data=raw,
            filename=f"memory_{agent_id}_{memory_type}_{datetime.now(UTC).isoformat()}.json",
            pin=pin,
        )
        metadata = MemoryMetadata(
            agent_id=agent_id,
            memory_type=memory_type,
            timestamp=result.timestamp,
            tags=tags,
            integrity_hash=result.cid,
        )
        self._memories[result.cid] = (memory_data, metadata)
        return MemoryUploadResult(
            cid=result.cid,
            size=size,
            compressed_size=size,  # IPFS handles dedup; we report original size
            upload_time=result.timestamp,
            pinned=pin,
        )

    async def retrieve_memory(self, cid: str, verify_integrity: bool = True) -> tuple[dict[str, Any], MemoryMetadata]:
        """Retrieve memory data from IPFS by CID.

        Returns (memory_data, metadata) tuple.
        Raises ValueError if CID is not found.
        """
        # Check in-memory cache first
        if cid in self._memories:
            return self._memories[cid]
        # Fetch from IPFS
        content = await self.client.get_content(cid)
        if content is None:
            raise ValueError(f"Content not found for CID: {cid}")
        data = json.loads(content.decode("utf-8"))
        metadata = MemoryMetadata(
            agent_id="unknown",
            memory_type="unknown",
            timestamp=datetime.now(UTC),
            integrity_hash=cid,
        )
        return data, metadata

    async def batch_upload_memories(
        self,
        agent_id: str,
        memories: list[tuple[dict[str, Any], str, list[str]]],
        batch_size: int = 10,
    ) -> list[MemoryUploadResult]:
        """Upload multiple memories in batches."""
        results: list[MemoryUploadResult] = []
        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]
            for memory_data, memory_type, tags in batch:
                result = await self.upload_memory(
                    agent_id=agent_id,
                    memory_data=memory_data,
                    memory_type=memory_type,
                    tags=tags,
                )
                results.append(result)
        return results

    async def create_filecoin_deal(self, cid: str, duration: int = 180) -> str | None:
        """Create a Filecoin storage deal for a CID.

        Returns deal_id or None if Filecoin integration is not configured.
        """
        # Filecoin deal creation requires a Filecoin node or broker API.
        # Not configured on this node — return None honestly.
        logger.warning("Filecoin deal creation not configured (cid=%s)", cid)
        return None

    async def list_agent_memories(self, agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """List memory CIDs for an agent."""
        cids = []
        for cid, (_, metadata) in self._memories.items():
            if metadata.agent_id == agent_id:
                cids.append({"cid": cid, "memory_type": metadata.memory_type, "timestamp": metadata.timestamp.isoformat()})
            if len(cids) >= limit:
                break
        return cids

    async def delete_memory(self, cid: str) -> bool:
        """Delete/unpin a memory from IPFS."""
        success = await self.client.unpin_cid(cid)
        if success:
            self._memories.pop(cid, None)
        return success

    async def get_storage_stats(self) -> dict[str, Any]:
        """Get IPFS storage statistics."""
        available = await self.client.check_availability()
        pins = await self.client.list_pins() if available else []
        return {
            "ipfs_available": available,
            "total_pinned": len(pins),
            "total_memories": len(self._memories),
            "total_uploads": len(self._uploads),
            "api_url": self.client.api_url,
        }

    async def health_check(self) -> dict[str, Any]:
        """Check IPFS service health"""
        available = await self.client.check_availability()
        return {
            "status": "healthy" if available else "degraded",
            "ipfs_node_available": available,
            "api_url": self.client.api_url,
            "gateway_url": self.client.gateway_url,
            "stored_uploads": len(self._uploads),
        }


_ipfs_service: IPFSService | None = None


def get_ipfs_service() -> IPFSService:
    """Get global IPFS service"""
    global _ipfs_service
    if _ipfs_service is None:
        _ipfs_service = IPFSService()
    return _ipfs_service
