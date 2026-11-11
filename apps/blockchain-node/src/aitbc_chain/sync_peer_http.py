"""Bounded JSON reads from operator-configured sync peers."""

from __future__ import annotations

import json
from typing import Any

import httpx


class PeerResponseTooLarge(Exception):
    """A peer sync response exceeded the configured decompressed-size cap."""


async def get_json_bounded(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    max_bytes: int,
) -> Any:
    """GET *url* and parse JSON with a decompressed-body cap (#1627, #1594).

    ``client.get`` + ``resp.json()`` buffers the entire body — and httpx
    transparently decodes gzip/deflate — before verification can run, so
    peers must be read via a byte stream and refused once *max_bytes* is exceeded.
    """
    chunks: list[bytes] = []
    total = 0
    async with client.stream("GET", url, params=params) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise PeerResponseTooLarge(f"sync response from {url} exceeds {max_bytes} bytes")
            chunks.append(chunk)
    return json.loads(b"".join(chunks))
