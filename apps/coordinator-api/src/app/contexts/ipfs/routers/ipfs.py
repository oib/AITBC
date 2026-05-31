"""IPFS storage router for Coordinator API"""


from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ....config import settings
from ....services.ipfs_storage_service import IPFSStorageService

router = APIRouter()


# Pydantic models for requests/responses
class IPFSUploadRequest(BaseModel):
    """Request model for IPFS upload"""
    agent_id: str
    memory_data: dict
    memory_type: str = "experience"
    tags: list[str] = Field(default_factory=list)
    compress: bool = True
    pin: bool = False


class IPFSRetrieveRequest(BaseModel):
    """Request model for IPFS retrieve"""
    cid: str
    verify_integrity: bool = True


class IPFSBatchUploadRequest(BaseModel):
    """Request model for batch IPFS upload"""
    agent_id: str
    memories: list[dict]
    batch_size: int = Field(default=10, ge=1, le=50)


class IPFSCreateDealRequest(BaseModel):
    """Request model for creating Filecoin deal"""
    cid: str
    duration: int = Field(default=180, ge=1)


class IPFSDeleteRequest(BaseModel):
    """Request model for IPFS delete"""
    cid: str


# Singleton IPFS service instance
_ipfs_service_instance: IPFSStorageService | None = None

def get_ipfs_service() -> None:
    """Get IPFS storage service instance (singleton)"""
    global _ipfs_service_instance
    if _ipfs_service_instance is None:
        config = {
            "ipfs_url": settings.ipfs_url if hasattr(settings, 'ipfs_url') else "/ip4/127.0.0.1/tcp/5001",
            "blockchain_enabled": False,
            "compression_threshold": 1024,
            "pin_threshold": 100,
        }
        _ipfs_service_instance = IPFSStorageService(config)
    return _ipfs_service_instance  # type: ignore[return-value]


@router.post("/upload")
async def upload_memory(request: IPFSUploadRequest) -> None:
    """Upload agent memory data to IPFS"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        result = await service.upload_memory(  # type: ignore[attr-defined]
            agent_id=request.agent_id,
            memory_data=request.memory_data,
            memory_type=request.memory_type,
            tags=request.tags,
            compress=request.compress,
            pin=request.pin,
        )

        return {  # type: ignore[return-value]
            "success": True,
            "cid": result.cid,
            "size": result.size,
            "compressed_size": result.compressed_size,
            "upload_time": result.upload_time.isoformat(),
            "pinned": result.pinned,
            "filecoin_deal": result.filecoin_deal,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/retrieve")
async def retrieve_memory(request: IPFSRetrieveRequest) -> None:
    """Retrieve memory data from IPFS by CID"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        memory_data, metadata = await service.retrieve_memory(  # type: ignore[attr-defined]
            cid=request.cid,
            verify_integrity=request.verify_integrity,
        )

        return {  # type: ignore[return-value]
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieve failed: {str(e)}")


@router.post("/batch-upload")
async def batch_upload_memories(request: IPFSBatchUploadRequest) -> None:
    """Upload multiple memories in batches to IPFS"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        # Convert memories to tuples for the service
        memory_tuples = [(mem.get("data", {}), mem.get("type", "experience"), mem.get("tags", [])) for mem in request.memories]

        results = await service.batch_upload_memories(  # type: ignore[attr-defined]
            agent_id=request.agent_id,
            memories=memory_tuples,
            batch_size=request.batch_size,
        )

        return {  # type: ignore[return-value]
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {str(e)}")


@router.post("/create-deal")
async def create_filecoin_deal(request: IPFSCreateDealRequest) -> None:
    """Create Filecoin storage deal for CID persistence"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        deal_id = await service.create_filecoin_deal(  # type: ignore[attr-defined]
            cid=request.cid,
            duration=request.duration,
        )

        if deal_id is None:
            raise HTTPException(status_code=500, detail="Failed to create Filecoin deal")

        return {  # type: ignore[return-value]
            "success": True,
            "deal_id": deal_id,
            "cid": request.cid,
            "duration": request.duration,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deal creation failed: {str(e)}")


@router.get("/list/{agent_id}")
async def list_agent_memories(  # type: ignore[no-untyped-def]
    agent_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
):
    """List all memory CIDs for an agent"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        cids = await service.list_agent_memories(agent_id=agent_id, limit=limit)  # type: ignore[attr-defined]

        return {
            "success": True,
            "agent_id": agent_id,
            "total": len(cids),
            "cids": cids,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List failed: {str(e)}")


@router.delete("/delete")
async def delete_memory(request: IPFSDeleteRequest) -> None:
    """Delete/unpin memory from IPFS"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        success = await service.delete_memory(cid=request.cid)  # type: ignore[attr-defined]

        if not success:
            raise HTTPException(status_code=404, detail=f"Failed to delete CID {request.cid}")

        return {  # type: ignore[return-value]
            "success": True,
            "message": f"Memory {request.cid} deleted successfully",
            "cid": request.cid,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/stats")
async def get_storage_stats() -> None:
    """Get IPFS storage statistics"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        stats = await service.get_storage_stats()  # type: ignore[attr-defined]

        return {  # type: ignore[return-value]
            "success": True,
            "stats": stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/health")
async def health_check() -> None:
    """Health check for IPFS service"""
    try:
        service = get_ipfs_service()  # type: ignore[func-returns-value]
        await service.initialize()  # type: ignore[attr-defined]

        return {  # type: ignore[return-value]
            "status": "healthy",
            "service": "ipfs-storage",
            "message": "IPFS service is operational",
        }
    except Exception as e:
        return {  # type: ignore[return-value]
            "status": "unhealthy",
            "service": "ipfs-storage",
            "message": f"IPFS service error: {str(e)}",
        }
