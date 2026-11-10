"""Memory service REST API."""

from __future__ import annotations

import base64
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from .config import settings
from .service import BlobPermissionError, BlobTooLargeError, MemoryStore, StoreFullError

router = APIRouter(tags=["memory"])
store = MemoryStore()


async def require_api_key(request: Request) -> None:
    """Shared-secret gate (#1682): enforced only when MEMORY_API_KEY is set.

    Constant-time compare, same pattern as the hermes /run credential. When
    unset the service keeps its previous open behavior — the per-blob owner
    checks on /retrieve and DELETE still apply either way.
    """
    if not settings.memory_api_key:
        return
    token = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(token, settings.memory_api_key):
        raise HTTPException(status_code=401, detail="invalid or missing api key")


class StoreRequest(BaseModel):
    """Payload for storing a blob."""

    owner: str
    data: str  # base64-encoded bytes
    tags: dict[str, Any] = {}


class StoreResponse(BaseModel):
    """Response after storing a blob."""

    content_address: str
    owner: str
    size: int
    tags: dict[str, Any]
    created_at: str


class RetrieveResponse(BaseModel):
    """Response when retrieving a blob."""

    content_address: str
    owner: str
    size: int
    data: str  # base64-encoded bytes
    tags: dict[str, Any]
    created_at: str


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Service health check."""
    return store.health()


@router.post("/store", response_model=StoreResponse, status_code=201, dependencies=[Depends(require_api_key)])
@rate_limit(rate=100, per=60)
async def store_blob(request: Request, body: StoreRequest) -> dict[str, Any]:
    """Store a content-addressed blob."""

    # Reject on the encoded length before decoding so an oversize body never
    # materialises as bytes (base64 inflates by ~4/3 plus padding).
    if len(body.data) > (settings.memory_max_blob_bytes * 4) // 3 + 4:
        raise HTTPException(status_code=413, detail=f"blob exceeds the {settings.memory_max_blob_bytes}-byte cap")
    try:
        data = base64.b64decode(body.data)
        blob = store.store_blob(body.owner, data, body.tags)
        return {
            "content_address": blob.content_address,
            "owner": blob.owner,
            "size": blob.size,
            "tags": blob.tags,
            "created_at": blob.created_at.isoformat(),
        }
    except BlobTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except StoreFullError as e:
        raise HTTPException(status_code=507, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/retrieve/{content_address}",
    response_model=RetrieveResponse,
    dependencies=[Depends(require_api_key)],
)
@rate_limit(rate=200, per=60)
async def retrieve_blob(
    request: Request,
    content_address: str,
    owner: str = Query(..., min_length=1, description="Owner identity; must match a storing owner"),
) -> dict[str, Any]:
    """Retrieve a blob by content address.

    ``owner`` is required (#1682): the route previously ignored ownership
    entirely, so any caller who learned a cid could read the blob. Every
    tenant that stored the content is recorded as an owner, so idempotent
    re-stores by a second tenant do not lock that tenant out.
    """
    try:
        data, blob = store.retrieve_blob(content_address, owner)
        return {
            "content_address": blob.content_address,
            "owner": blob.owner,
            "size": blob.size,
            "data": base64.b64encode(data).decode("ascii"),
            "tags": blob.tags,
            "created_at": blob.created_at.isoformat(),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BlobPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/blobs/{content_address}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
@rate_limit(rate=100, per=60)
async def delete_blob(
    request: Request,
    content_address: str,
    owner: str = Query(..., min_length=1, description="Owner identity; must match a storing owner"),
) -> None:
    """Delete a blob. Only an owner of the blob may delete it (#1682)."""
    try:
        store.delete_blob(content_address, owner)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BlobPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
