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
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

_OPS_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    httpx.HTTPError,
)

# IPFS-DEPTH-1 (#1582): Kubo pin/add, pin/rm and cat take an *IPFS path* arg,
# not just a bare CID — "ipfs/<cid>", "/ipfs/<cid>" or ".." segments can reach
# repo objects outside the DAG. Only bare CIDs (alphanumeric base32/base58/
# base36 spellings) are accepted; anything with a separator is refused before
# it reaches the daemon.
_CID_ARG_RE = re.compile(r"[A-Za-z0-9]{1,256}")


def _validate_cid_arg(cid: str) -> str:
    """Return ``cid`` if it is a bare CID-shaped arg, else raise ValueError."""
    if not isinstance(cid, str) or not _CID_ARG_RE.fullmatch(cid):
        raise ValueError(f"Invalid CID argument: {cid!r}")
    return cid


# #1932 F2: ``cat`` responses were buffered whole — a buyer-chosen CID could
# pin coordinator memory through /ipfs/retrieve. Reads are now streamed and
# capped; the default sits well above the 4 MiB per-upload memory cap while
# still bounding a hostile object. Override with AITBC_IPFS_MAX_CONTENT_BYTES.
_MAX_CONTENT_BYTES_ENV = "AITBC_IPFS_MAX_CONTENT_BYTES"
_DEFAULT_MAX_CONTENT_BYTES = 16 * 1024 * 1024


def _max_content_bytes() -> int:
    try:
        return max(1, int(os.environ.get(_MAX_CONTENT_BYTES_ENV, _DEFAULT_MAX_CONTENT_BYTES)))
    except ValueError:
        return _DEFAULT_MAX_CONTENT_BYTES


async def _bounded_body(response: httpx.Response, cap: int) -> bytes:
    """Read a streaming response body, refusing once it exceeds *cap* bytes."""
    length = response.headers.get("Content-Length")
    try:
        declared = int(length) if length is not None else None
    except ValueError:
        declared = None
    if declared is not None and declared > cap:
        raise ValueError(f"IPFS content length {declared} exceeds the {cap}-byte cap")
    buf = bytearray()
    async for chunk in response.aiter_bytes():
        buf += chunk
        if len(buf) > cap:
            raise ValueError(f"IPFS content exceeds the {cap}-byte cap")
    return bytes(buf)


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
        api_url: str = "http://localhost:5001",  # ponytail: default is local dev, override in production
        gateway_url: str = "https://ipfs.io",
        pinning_service: str | None = None,
        pinning_key: str | None = None,
        session: Any = None,
        public_gateway_fallback: bool = False,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.pinning_service = pinning_service
        self.pinning_key = pinning_key
        # IPFS-DEPTH-1 (#1582): fetching through the public ipfs.io gateway
        # leaks every retrieved CID to a third party. It stays available only
        # as an explicit opt-in for nodes whose content lives on the public
        # swarm; the default is local-Kubo ``cat`` only.
        self.public_gateway_fallback = public_gateway_fallback
        self._client = httpx.AsyncClient(timeout=60.0, limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))
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
        except _OPS_ERRORS as e:
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
        except _OPS_ERRORS as e:
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
        except _OPS_ERRORS as e:
            logger.warning("External pinning failed: %s", e)
            return False

    async def get_content(self, cid: str, max_bytes: int | None = None) -> bytes | None:
        """Retrieve content from IPFS by CID via the local Kubo node.

        ``/api/v0/cat`` resolves CIDv0 and CIDv1 and never leaves the island
        swarm. The public gateway is only consulted when
        ``public_gateway_fallback`` was explicitly enabled — every fallback
        fetch would otherwise hand the CID to ipfs.io. The body is streamed
        and capped at ``max_bytes`` (default ``AITBC_IPFS_MAX_CONTENT_BYTES``)
        so a large object cannot be buffered whole (#1932 F2).
        """
        cid = _validate_cid_arg(cid)
        cap = _max_content_bytes() if max_bytes is None else max(1, int(max_bytes))
        try:
            async with self._client.stream(
                "POST", f"{self.api_url}/api/v0/cat", params={"arg": cid}, timeout=30.0
            ) as response:
                if response.status_code == 200:
                    return await _bounded_body(response, cap)
        except ValueError:
            raise  # a size-cap refusal is a caller-visible error, not a miss
        except _OPS_ERRORS as e:
            logger.debug("Could not fetch CID %s from local IPFS node: %s", cid, e)
        if self.public_gateway_fallback:
            try:
                async with self._client.stream(
                    "GET", f"{self.gateway_url}/ipfs/{cid}", timeout=30.0, follow_redirects=True
                ) as response:
                    if response.status_code == 200:
                        return await _bounded_body(response, cap)
            except ValueError:
                raise
            except _OPS_ERRORS as e:
                logger.debug("Could not fetch from IPFS gateway: %s", e)
        return None

    async def pin_cid(self, cid: str, name: str = "") -> bool:
        """Pin an existing CID to the local node"""
        cid = _validate_cid_arg(cid)
        if not await self.check_availability():
            return False
        try:
            response = await self._client.post(f"{self.api_url}/api/v0/pin/add", params={"arg": cid}, timeout=30.0)
            return response.status_code == 200
        except _OPS_ERRORS as e:
            logger.warning("Pin failed: %s", e)
            return False

    async def unpin_cid(self, cid: str) -> bool:
        """Unpin a CID from the local node"""
        cid = _validate_cid_arg(cid)
        if not await self.check_availability():
            return False
        try:
            response = await self._client.post(f"{self.api_url}/api/v0/pin/rm", params={"arg": cid}, timeout=30.0)
            return response.status_code == 200
        except _OPS_ERRORS as e:
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
        except _OPS_ERRORS as e:
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

    # IPFS-DEPTH-1 (#1582): unbounded pin/upload let any caller fill the Kubo
    # repo and leak memory in the process-lifetime registries below.
    DEFAULT_MAX_MEMORY_BYTES = 4 * 1024 * 1024
    DEFAULT_REGISTRY_MAX = 10_000
    DEFAULT_MAX_BATCH_MEMORIES = 50
    DEFAULT_MAX_TAGS = 32

    def __init__(self, session: Any = None) -> None:
        # Accept either a DB session (legacy) or a config dict (router pattern)
        if isinstance(session, dict):
            config = session
            api_url = config.get("ipfs_url", "http://localhost:5001")
            self.client = IPFSClient(
                api_url=api_url,
                public_gateway_fallback=bool(config.get("ipfs_public_gateway_fallback", False)),
            )
            self._max_memory_bytes = int(config.get("ipfs_max_memory_bytes", self.DEFAULT_MAX_MEMORY_BYTES))
            self._registry_max = int(config.get("ipfs_registry_max", self.DEFAULT_REGISTRY_MAX))
            self._max_batch_memories = int(config.get("ipfs_max_batch_memories", self.DEFAULT_MAX_BATCH_MEMORIES))
        else:
            self.client = IPFSClient()
            self._max_memory_bytes = self.DEFAULT_MAX_MEMORY_BYTES
            self._registry_max = self.DEFAULT_REGISTRY_MAX
            self._max_batch_memories = self.DEFAULT_MAX_BATCH_MEMORIES
        # OrderedDict LRU registries — bounded so a long-lived coordinator
        # cannot grow them without limit (#1582).
        self._uploads: OrderedDict[str, IPFSUploadResult] = OrderedDict()
        self._memories: OrderedDict[str, tuple[dict[str, Any], MemoryMetadata]] = OrderedDict()
        self.session = session if not isinstance(session, dict) else None

    def _remember_upload(self, key: str, result: IPFSUploadResult) -> None:
        self._uploads[key] = result
        self._uploads.move_to_end(key)
        while len(self._uploads) > self._registry_max:
            self._uploads.popitem(last=False)

    def _remember_memory(self, cid: str, data: dict[str, Any], metadata: MemoryMetadata) -> None:
        self._memories[cid] = (data, metadata)
        self._memories.move_to_end(cid)
        while len(self._memories) > self._registry_max:
            self._memories.popitem(last=False)

    def _owned_cids(self) -> set[str]:
        """CIDs this service instance uploaded — the only ones delete may unpin."""
        owned = set(self._memories)
        owned.update(r.cid for r in self._uploads.values() if r.cid)
        return owned

    async def initialize(self) -> None:
        """Initialize the service — check IPFS node availability."""
        await self.client.check_availability()

    async def store_job_result(self, job_id: str, result_data: dict[str, Any]) -> IPFSUploadResult:
        """Store AI job result on IPFS"""
        data = json.dumps(result_data, indent=2).encode("utf-8")
        result = await self.client.upload_file(data=data, filename=f"job_{job_id}_result.json", pin=True)
        self._remember_upload(job_id, result)
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
        pin: bool = True,
    ) -> MemoryUploadResult:
        """Upload agent memory data to IPFS.

        Serializes the memory dict as JSON and uploads it via the IPFS client.
        Raises RuntimeError if IPFS node is unavailable (no mock CIDs).

        ``pin`` defaults to True (V13-RES2-IPFS-GC-1, #1713): the island
        daemon runs ``ipfs daemon --enable-gc``, so an unpinned CID is
        collectable while the memory record still references it. Callers
        that genuinely want a transient object can pass ``pin=False``.
        """
        tags = (tags or [])[: self.DEFAULT_MAX_TAGS]
        raw = json.dumps(memory_data, indent=2).encode("utf-8")
        size = len(raw)
        if size > self._max_memory_bytes:
            raise ValueError(
                f"memory_data serializes to {size} bytes, exceeding the {self._max_memory_bytes}-byte per-upload cap"
            )
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
        self._remember_memory(result.cid, memory_data, metadata)
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
        if len(memories) > self._max_batch_memories:
            raise ValueError(f"batch of {len(memories)} memories exceeds the {self._max_batch_memories}-memory cap")
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
        """Delete/unpin a memory from IPFS.

        IPFS-DEPTH-1 (#1582): only CIDs this service instance uploaded may be
        unpinned — the shared Kubo node also holds pins owned by other
        tenants (store_job_result, store_evidence, provider rentals), and an
        unscoped ``pin/rm`` was a cross-tenant destruction primitive. A CID
        outside the upload registries returns False (404 at the router); the
        operator path for daemon-side pins remains ``ipfs pin rm``.
        """
        if cid not in self._owned_cids():
            logger.warning("Refusing to unpin CID %s: not uploaded via this service", cid)
            return False
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
