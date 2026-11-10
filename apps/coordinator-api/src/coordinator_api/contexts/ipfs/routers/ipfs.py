"""IPFS storage router for Coordinator API"""

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ....config import settings
from ..services.ipfs_service import IPFSService
from ..services.island_ipfs_access import get_member_swarm_key, issue_swarm_key_nonce
from aitbc.rate_limiting import rate_limit

router = APIRouter()


# Pydantic models for requests/responses
class IPFSUploadRequest(BaseModel):
    """Request model for IPFS upload"""

    agent_id: str
    memory_data: dict[str, Any]
    memory_type: str = "experience"
    tags: list[str] = Field(default_factory=list)
    compress: bool = True
    # #1713: island daemon runs --enable-gc; unpinned memory CIDs are
    # collectable while still referenced — pin by default.
    pin: bool = True


class IPFSRetrieveRequest(BaseModel):
    """Request model for IPFS retrieve"""

    cid: str
    verify_integrity: bool = True


class IPFSBatchUploadRequest(BaseModel):
    """Request model for batch IPFS upload"""

    agent_id: str
    # IPFS-DEPTH-1 (#1582): the memories list was unbounded — cap it at the
    # service's batch ceiling so one request cannot pin arbitrary counts.
    memories: list[dict[str, Any]] = Field(max_length=50)
    batch_size: int = Field(default=10, ge=1, le=50)


class IPFSCreateDealRequest(BaseModel):
    """Request model for creating Filecoin deal"""

    cid: str
    duration: int = Field(default=180, ge=1)


class IPFSDeleteRequest(BaseModel):
    """Request model for IPFS delete"""

    cid: str


class IslandSwarmKeyRequest(BaseModel):
    """Request model for retrieving an island's private IPFS swarm key."""

    chain_id: str
    island_id: str
    member_address: str
    nonce: str
    signature: str


class IslandSwarmKeyNonceRequest(BaseModel):
    """Request model for a server-issued swarm-key challenge nonce."""

    chain_id: str
    island_id: str
    member_address: str


# Singleton IPFS service instance
_ipfs_service_instance: IPFSService | None = None


def get_ipfs_service() -> IPFSService:
    """Get IPFS storage service instance (singleton)"""
    global _ipfs_service_instance
    if _ipfs_service_instance is None:
        config = {
            "ipfs_url": settings.ipfs_url if hasattr(settings, "ipfs_url") else "/ip4/127.0.0.1/tcp/5001",
            "blockchain_enabled": False,
            "compression_threshold": 1024,
            "pin_threshold": 100,
            # IPFS-DEPTH-1 (#1582) bounds — env-overridable, sane defaults.
            "ipfs_max_memory_bytes": int(os.environ.get("AITBC_IPFS_MAX_MEMORY_BYTES", str(4 * 1024 * 1024))),
            "ipfs_registry_max": int(os.environ.get("AITBC_IPFS_REGISTRY_MAX", "10000")),
            "ipfs_max_batch_memories": int(os.environ.get("AITBC_IPFS_MAX_BATCH_MEMORIES", "50")),
            # Public-gateway fetch leaks CIDs to ipfs.io — opt-in only.
            "ipfs_public_gateway_fallback": os.environ.get("AITBC_IPFS_PUBLIC_GATEWAY_FALLBACK", "").lower()
            in ("1", "true", "yes"),
        }
        _ipfs_service_instance = IPFSService(config)
    return _ipfs_service_instance


@router.post("/upload")
@rate_limit(rate=20, per=60)
async def upload_memory(request: IPFSUploadRequest, *, http_request: Request) -> dict[str, Any]:
    """Upload agent memory data to IPFS"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        result = await service.upload_memory(
            agent_id=request.agent_id,
            memory_data=request.memory_data,
            memory_type=request.memory_type,
            tags=request.tags,
            compress=request.compress,
            pin=request.pin,
        )

        return {
            "success": True,
            "cid": result.cid,
            "size": result.size,
            "compressed_size": result.compressed_size,
            "upload_time": result.upload_time.isoformat(),
            "pinned": result.pinned,
            "filecoin_deal": result.filecoin_deal,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/retrieve")
@rate_limit(rate=60, per=60)
async def retrieve_memory(request: IPFSRetrieveRequest, *, http_request: Request) -> dict[str, Any]:
    """Retrieve memory data from IPFS by CID"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        memory_data, metadata = await service.retrieve_memory(
            cid=request.cid,
            verify_integrity=request.verify_integrity,
        )

        return {
            "success": True,
            "cid": request.cid,
            "memory_data": memory_data,
            "metadata": {
                "agent_id": metadata.agent_id,
                "memory_type": metadata.memory_type,
                "timestamp": metadata.timestamp.isoformat(),
                "version": metadata.version,
                "tags": metadata.tags,
                "compression_ratio": metadata.compression_ratio,
                "integrity_hash": metadata.integrity_hash,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/batch-upload")
@rate_limit(rate=20, per=60)
async def batch_upload_memories(request: IPFSBatchUploadRequest, *, http_request: Request) -> dict[str, Any]:
    """Upload multiple memories in batches to IPFS"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        # Convert memories to tuples for the service
        memory_tuples = [(mem.get("data", {}), mem.get("type", "experience"), mem.get("tags", [])) for mem in request.memories]

        results = await service.batch_upload_memories(
            agent_id=request.agent_id,
            memories=memory_tuples,
            batch_size=request.batch_size,
        )

        return {
            "success": True,
            "total_uploaded": len(results),
            "results": [
                {
                    "cid": r.cid,
                    "size": r.size,
                    "compressed_size": r.compressed_size,
                    "pinned": r.pinned,
                }
                for r in results
            ],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/create-deal")
@rate_limit(rate=20, per=60)
async def create_filecoin_deal(request: IPFSCreateDealRequest, *, http_request: Request) -> dict[str, Any]:
    """Create Filecoin storage deal for CID persistence"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        deal_id = await service.create_filecoin_deal(
            cid=request.cid,
            duration=request.duration,
        )

        if deal_id is None:
            raise HTTPException(status_code=500, detail="Failed to create Filecoin deal")

        return {
            "success": True,
            "deal_id": deal_id,
            "cid": request.cid,
            "duration": request.duration,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/list/{agent_id}")
async def list_agent_memories(
    agent_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    """List all memory CIDs for an agent"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        cids = await service.list_agent_memories(agent_id=agent_id, limit=limit)

        return {
            "success": True,
            "agent_id": agent_id,
            "total": len(cids),
            "cids": cids,
        }
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/delete")
@rate_limit(rate=20, per=60)
async def delete_memory(request: IPFSDeleteRequest, *, http_request: Request) -> dict[str, Any]:
    """Delete/unpin memory from IPFS"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        success = await service.delete_memory(cid=request.cid)

        if not success:
            raise HTTPException(status_code=404, detail=f"Failed to delete CID {request.cid}")

        return {
            "success": True,
            "message": f"Memory {request.cid} deleted successfully",
            "cid": request.cid,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/stats")
async def get_storage_stats() -> dict[str, Any]:
    """Get IPFS storage statistics"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        stats = await service.get_storage_stats()

        return {
            "success": True,
            "stats": stats,
        }
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check for IPFS service"""
    try:
        service = get_ipfs_service()
        await service.initialize()

        return {
            "status": "healthy",
            "service": "ipfs-storage",
            "message": "IPFS service is operational",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "ipfs-storage",
            "message": f"IPFS service error: {str(e)}",
        }


@router.post("/island/swarm-key/nonce")
@rate_limit(rate=20, per=60)
def issue_island_swarm_key_nonce(request: IslandSwarmKeyNonceRequest, *, http_request: Request) -> dict[str, Any]:
    """Issue a single-use, expiring swarm-key challenge nonce (#1712).

    The nonce is bound to (chain_id, island_id, member_address); the member
    signs it and posts the signature to /island/swarm-key within the TTL.
    """
    try:
        return {"success": True, **issue_swarm_key_nonce(request.chain_id, request.island_id, request.member_address)}
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/island/swarm-key")
@rate_limit(rate=20, per=60)
def get_island_swarm_key(request: IslandSwarmKeyRequest, *, http_request: Request) -> dict[str, Any]:
    """Return the private IPFS swarm key for an island to a paid, verified member."""
    try:
        result = get_member_swarm_key(
            chain_id=request.chain_id,
            island_id=request.island_id,
            member_address=request.member_address,
            nonce=request.nonce,
            signature=request.signature,
        )
        return {"success": True, **result}
    except PermissionError as e:
        logging.getLogger(__name__).warning(
            "Swarm-key request denied for %s on %s: %s", request.member_address, request.island_id, e
        )
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logging.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e
