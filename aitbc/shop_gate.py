"""Per-job buyer access-token gate for shop endpoints (SHOP-ENDPOINTS-NO-PAYMENT-GATE-1, #803).

Ruling 6A: a paid shop call carries the per-job access token the market
service issued when the escrow locked — ``X-Access-Key`` +
``X-Access-Secret``, bound strictly to the job via ``X-Job-Id`` (ruling
8222). The gate verifies the token against the market service's existing
job-access endpoint (``GET /v1/market/access/{key}?access_secret=``), which
already enforces hashed-secret match and rejects jobs outside
``QUEUED``/``RUNNING`` (including completed/released and other terminal
states) plus expired unfinished jobs.

Wire as a FastAPI dependency on paid routes::

    @app.post("/process", dependencies=[Depends(require_job_access)])

Public routes (health, capabilities, models) stay ungated. The market URL
comes from ``MARKET_VERIFY_URL`` (default http://127.0.0.1:8102).

APIGW-OLLAMA-DEPTH2-1 (#1613): the verifier used to build a fresh
``httpx.AsyncClient`` per call (no connection pooling) and send
``access_secret`` as a URL query parameter, where it lands in market access
logs. Verification now rides one shared pooled client for the process
lifetime and carries the secret in the ``X-Access-Secret`` header — the
market endpoint accepts it there (query param still works for older
callers). The client is created lazily on first use so importing this
module never binds it to an event loop.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import HTTPException, Request, status

if TYPE_CHECKING:
    import httpx

MARKET_VERIFY_URL = os.environ.get("MARKET_VERIFY_URL", "http://127.0.0.1:8102")
VERIFY_TIMEOUT = float(os.environ.get("MARKET_VERIFY_TIMEOUT", "10"))

# Access keys are token_urlsafe output — a single safe path segment only.
# Anything else (notably "../jobs/<id>" traversal against the verify URL)
# is refused before any market call (SHOPGATE-ACCESS-KEY-PATH-TRAVERSAL-1).
_ACCESS_KEY_RE = re.compile(r"[A-Za-z0-9_-]{8,128}")

_client: httpx.AsyncClient | None = None


def _verify_client() -> httpx.AsyncClient:
    """Shared pooled httpx.AsyncClient for market verify calls."""
    global _client
    if _client is None:
        import httpx

        _client = httpx.AsyncClient(timeout=VERIFY_TIMEOUT)
    return _client


async def _verify(access_key: str, access_secret: str) -> dict[str, Any] | None:
    """Return the job dict when the token validates, else None."""
    import httpx

    try:
        resp = await _verify_client().get(
            f"{MARKET_VERIFY_URL}/v1/market/access/{quote(access_key, safe='')}",
            headers={"X-Access-Secret": access_secret},
            timeout=VERIFY_TIMEOUT,
        )
    except httpx.HTTPError:
        # The gate is paid work; a dead verifier must not silently pass.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="access-token verification unavailable",
        ) from None
    if resp.status_code != 200:
        return None
    try:
        data: Any = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def require_job_access(request: Request) -> dict[str, Any]:
    """FastAPI dependency: 401/403 unless the request carries a valid paid-job token.

    Strict job-id binding (ruling 8222): ``X-Job-Id`` is required and must
    equal the job the token was issued for — a valid token for job A does
    not buy work on job B.
    """
    access_key = request.headers.get("X-Access-Key")
    access_secret = request.headers.get("X-Access-Secret")
    job_id = request.headers.get("X-Job-Id")
    if not access_key or not access_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="access token required")
    if not _ACCESS_KEY_RE.fullmatch(access_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")
    if not job_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Job-Id required")
    job = await _verify(access_key, access_secret)
    if job is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token")
    if job.get("job_id") != job_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access token not issued for this job",
        )
    return job
