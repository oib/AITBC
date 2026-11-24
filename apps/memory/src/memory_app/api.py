"""Memory service REST API."""

from __future__ import annotations

import base64
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from aitbc.rate_limiting import rate_limit

from .config import settings
from .service import BlobPermissionError, BlobTooLargeError, MemoryStore, StoreFullError

router = APIRouter(tags=["memory"])
store = MemoryStore()


def _key_owner_map() -> dict[str, str]:
    """Parse MEMORY_API_KEY_OWNERS (JSON ``{"<key>": "<owner>"}``)."""
    raw = settings.memory_api_key_owners
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        logging.getLogger(__name__).error("MEMORY_API_KEY_OWNERS is not valid JSON — ignoring")
        return {}
    if not isinstance(parsed, dict):
        logging.getLogger(__name__).error("MEMORY_API_KEY_OWNERS must be a JSON object — ignoring")
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


async def require_api_key(request: Request) -> str | None:
    """Shared-secret gate (#1682) returning the authenticated owner identity.

    Constant-time compare, same pattern as the hermes /run credential.
    Returns ``None`` when no key material is configured (open mode — the
    per-blob owner checks still apply, self-asserted as before). With
    MEMORY_API_KEY set, every caller authenticates as the single tenant
    ``"shared"``; with MEMORY_API_KEY_OWNERS entries, the presented key
    binds the caller to that entry's owner (#2801). Either way the
    caller-supplied owner is ignored once authenticated — cross-tenant
    read/delete is impossible.
    """
    owners = _key_owner_map()
    if not settings.memory_api_key and not owners:
        return None
    token = request.headers.get("x-api-key", "")
    if settings.memory_api_key and hmac.compare_digest(token, settings.memory_api_key):
        return "shared"
    for key, owner in owners.items():
        if hmac.compare_digest(token, key):
            return owner
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


@router.post("/store", response_model=StoreResponse, status_code=201)
@rate_limit(rate=100, per=60)
async def store_blob(request: Request, body: StoreRequest, identity: str | None = Depends(require_api_key)) -> dict[str, Any]:
    """Store a content-addressed blob."""
    owner = identity or body.owner

    # Reject on the encoded length before decoding so an oversize body never
    # materialises as bytes (base64 inflates by ~4/3 plus padding).
    if len(body.data) > (settings.memory_max_blob_bytes * 4) // 3 + 4:
        raise HTTPException(status_code=413, detail=f"blob exceeds the {settings.memory_max_blob_bytes}-byte cap")
    try:
        data = base64.b64decode(body.data)
        blob = store.store_blob(owner, data, body.tags)
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
        logging.getLogger(__name__).warning("memory store full: %s", e)
        raise HTTPException(status_code=507, detail="memory store is full") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/retrieve/{content_address}", response_model=RetrieveResponse)
@rate_limit(rate=200, per=60)
async def retrieve_blob(
    request: Request,
    content_address: str,
    owner: str = Query(..., min_length=1, description="Owner identity; must match a storing owner"),
    identity: str | None = Depends(require_api_key),
) -> dict[str, Any]:
    """Retrieve a blob by content address.

    ``owner`` is required (#1682): the route previously ignored ownership
    entirely, so any caller who learned a cid could read the blob. Every
    tenant that stored the content is recorded as an owner, so idempotent
    re-stores by a second tenant do not lock that tenant out. When key
    auth is configured the authenticated identity overrides ``owner``
    (#2801) — the caller cannot assert another tenant's name.
    """
    try:
        data, blob = store.retrieve_blob(content_address, identity or owner)
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


@router.delete("/blobs/{content_address}", status_code=204)
@rate_limit(rate=100, per=60)
async def delete_blob(
    request: Request,
    content_address: str,
    owner: str = Query(..., min_length=1, description="Owner identity; must match a storing owner"),
    identity: str | None = Depends(require_api_key),
) -> None:
    """Delete a blob. Only an owner of the blob may delete it (#1682).

    Authenticated callers are bound to their key's owner identity (#2801).
    """
    try:
        store.delete_blob(content_address, identity or owner)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BlobPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
