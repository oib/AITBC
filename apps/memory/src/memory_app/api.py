"""Memory service REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from .service import MemoryStore

router = APIRouter(tags=["memory"])
store = MemoryStore()


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


@router.post("/store", response_model=StoreResponse, status_code=201)
@rate_limit(rate=100, per=60)
async def store_blob(request: Request, body: StoreRequest) -> dict[str, Any]:
    """Store a content-addressed blob."""
    import base64

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error storing blob: {e}") from e


@router.get("/retrieve/{content_address}", response_model=RetrieveResponse)
@rate_limit(rate=200, per=60)
async def retrieve_blob(request: Request, content_address: str) -> dict[str, Any]:
    """Retrieve a blob by content address."""
    try:
        data, blob = store.retrieve_blob(content_address)
        import base64

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving blob: {e}") from e
