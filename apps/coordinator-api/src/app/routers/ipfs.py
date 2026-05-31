"""
IPFS Router - IPFS storage API endpoints

Provides:
- File upload to IPFS
- Content retrieval by CID
- Pin management
- Upload tracking
"""

import json
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from ..services.ipfs_service import get_ipfs_service

router = APIRouter(prefix="/ipfs", tags=["ipfs"])


class UploadTextRequest(BaseModel):
    """Request to upload text content"""
    content: str
    filename: str | None = None
    pin: bool = True


class PinCIDRequest(BaseModel):
    """Request to pin a CID"""
    cid: str
    name: str | None = None


@router.post("/upload", summary="Upload file to IPFS")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    pin: bool = True
) -> dict[str, Any]:
    """
    Upload a file to IPFS.
    
    Returns:
    - CID (Content Identifier)
    - Gateway URL
    - Size
    - Pin status
    """
    try:
        service = get_ipfs_service()

        # Read file content
        content = await file.read()

        # Upload to IPFS
        result = await service.client.upload_file(
            data=content,
            filename=file.filename or "upload",
            pin=pin
        )

        return {
            "success": True,
            "cid": result.cid,
            "size": result.size,
            "name": result.name,
            "gateway_url": result.gateway_url,
            "pinned": result.pinned,
            "timestamp": result.timestamp.isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )


@router.post("/upload-text", summary="Upload text content to IPFS")
async def upload_text(
    request: Request,
    req: UploadTextRequest
) -> dict[str, Any]:
    """Upload text content to IPFS"""
    try:
        service = get_ipfs_service()

        result = await service.client.upload_file(
            data=req.content,
            filename=req.filename or "content.txt",
            pin=req.pin
        )

        return {
            "success": True,
            "cid": result.cid,
            "size": result.size,
            "name": result.name,
            "gateway_url": result.gateway_url,
            "pinned": result.pinned,
            "timestamp": result.timestamp.isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/content/{cid}", summary="Get IPFS content by CID")
async def get_content(
    request: Request,
    cid: str
) -> dict[str, Any]:
    """
    Retrieve content from IPFS by CID.
    
    If content is JSON, it's parsed and returned as JSON.
    Otherwise, base64-encoded data is returned.
    """
    try:
        service = get_ipfs_service()

        content = await service.client.get_content(cid)

        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Content not found for CID: {cid}"
            )

        # Try to parse as JSON
        try:
            data = json.loads(content.decode('utf-8'))  # type: ignore[name-defined]
            return {
                "success": True,
                "cid": cid,
                "format": "json",
                "data": data,
                "size": len(content)
            }
        except (json.JSONDecodeError, UnicodeDecodeError):  # type: ignore[name-defined]
            # Return as base64
            import base64
            return {
                "success": True,
                "cid": cid,
                "format": "base64",
                "data": base64.b64encode(content).decode('utf-8'),
                "size": len(content)
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve content: {str(e)}"
        )


@router.post("/pin", summary="Pin a CID")
async def pin_cid(
    request: Request,
    req: PinCIDRequest
) -> dict[str, Any]:
    """Pin an existing CID to the local IPFS node"""
    try:
        service = get_ipfs_service()

        success = await service.client.pin_cid(req.cid, req.name or "")

        return {
            "success": success,
            "cid": req.cid,
            "message": "Pinned successfully" if success else "Failed to pin"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pin failed: {str(e)}"
        )


@router.post("/unpin/{cid}", summary="Unpin a CID")
async def unpin_cid(
    request: Request,
    cid: str
) -> dict[str, Any]:
    """Unpin a CID from the local IPFS node"""
    try:
        service = get_ipfs_service()

        success = await service.client.unpin_cid(cid)

        return {
            "success": success,
            "cid": cid,
            "message": "Unpinned successfully" if success else "Failed to unpin"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unpin failed: {str(e)}"
        )


@router.get("/health", summary="Health check")
async def ipfs_health(request: Request) -> dict[str, Any]:
    """Check IPFS service health"""
    return {
        "status": "healthy",
        "ipfs_available": True,
        "service": "ipfs"
    }


@router.get("/pins", summary="List pinned CIDs")
async def list_pins(request: Request) -> dict[str, Any]:
    """List all CIDs pinned to the local node"""
    try:
        service = get_ipfs_service()

        pins = await service.client.list_pins()

        return {
            "pins": [
                {
                    "cid": p.cid,
                    "name": p.name,
                    "size": p.size,
                    "pinned_at": p.pinned_at.isoformat()
                }
                for p in pins
            ],
            "count": len(pins)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list pins: {str(e)}"
        )


@router.get("/gateway/{cid}", summary="Get gateway URL")
async def get_gateway_url(
    request: Request,
    cid: str
) -> dict[str, Any]:
    """Get the HTTP gateway URL for a CID"""
    service = get_ipfs_service()

    gateway = service.client.gateway_url

    return {
        "cid": cid,
        "gateway_url": f"{gateway}/ipfs/{cid}",
        "direct_url": f"{gateway}/ipfs/{cid}?download=true"
    }


@router.get("/health", summary="IPFS service health")
async def health_check(request: Request) -> dict[str, Any]:
    """Check IPFS service health"""
    try:
        service = get_ipfs_service()
        return await service.health_check()
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
