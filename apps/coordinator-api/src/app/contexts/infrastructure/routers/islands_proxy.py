"""Islands proxy router - forwards requests to edge-api service.

Uses a module-level shared ``httpx.AsyncClient`` to avoid per-request
TCP+TLS handshake overhead. The client is lazily created on first use
and reused across all proxy endpoints.
"""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

router = APIRouter(prefix="/islands", tags=["islands"])

# Edge API base URL
EDGE_API_BASE_URL = "http://127.0.0.1:8111/v1"

# Shared HTTP client for all proxy endpoints (lazily created)
_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=10.0)
    return _shared_client


async def aclose_client() -> None:
    """Close the shared HTTP client. Call during app shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


@router.get("/")
@rate_limit(rate=100, per=60)
async def list_islands(request: Request) -> dict[str, Any]:
    """List all islands (proxied to edge-api)"""
    client = _get_client()
    try:
        response = await client.get(f"{EDGE_API_BASE_URL}/islands/")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Edge API unavailable") from exc


@router.get("/{island_id}")
@rate_limit(rate=100, per=60)
async def get_island(island_id: str, request: Request) -> dict[str, Any]:
    """Get island details (proxied to edge-api)"""
    client = _get_client()
    try:
        response = await client.get(f"{EDGE_API_BASE_URL}/islands/{island_id}")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Island {island_id} not found") from exc
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Edge API unavailable") from exc


@router.post("/join")
@rate_limit(rate=20, per=60)
async def join_island(request: Request) -> dict[str, Any]:
    """Join an island (proxied to edge-api)"""
    client = _get_client()
    try:
        body = await request.json()
        response = await client.post(f"{EDGE_API_BASE_URL}/islands/join", json=body)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Edge API unavailable") from exc


@router.post("/leave")
@rate_limit(rate=20, per=60)
async def leave_island(request: Request) -> dict[str, Any]:
    """Leave an island (proxied to edge-api)"""
    client = _get_client()
    try:
        body = await request.json()
        response = await client.post(f"{EDGE_API_BASE_URL}/islands/leave", json=body)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Edge API unavailable") from exc


@router.post("/bridge")
@rate_limit(rate=20, per=60)
async def request_bridge(request: Request) -> dict[str, Any]:
    """Request bridge to another island (proxied to edge-api)"""
    client = _get_client()
    try:
        body = await request.json()
        response = await client.post(f"{EDGE_API_BASE_URL}/islands/bridge", json=body)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Edge API unavailable") from exc
