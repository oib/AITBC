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

import logging
import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import HTTPException, Request, status

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

_MARKET_VERIFY_DEFAULT = "http://127.0.0.1:8102"
MARKET_VERIFY_URL = os.environ.get("MARKET_VERIFY_URL", _MARKET_VERIFY_DEFAULT)
if "MARKET_VERIFY_URL" not in os.environ:
    # #2318: the implicit default assumes a market service on this host.
    # Shop nodes (whisper/ffmpeg/ollama-gate/hermes-agent) have none — every
    # gated call then fails 503 on connection-refused. This is a warning, not
    # an error: the market service itself legitimately uses the default.
    # Fix per host by setting MARKET_VERIFY_URL in the service env file
    # (e.g. /etc/aitbc/whisper.env) to the market endpoint.
    logger.warning(
        "MARKET_VERIFY_URL is unset; paid-job access-token verification uses the "
        "implicit default %s, which is only correct on hosts running the market "
        "service. On shop nodes set MARKET_VERIFY_URL in the service env file "
        "(e.g. /etc/aitbc/<service>.env) to the market endpoint or every gated "
        "call fails 503.",
        _MARKET_VERIFY_DEFAULT,
    )
VERIFY_TIMEOUT = float(os.environ.get("MARKET_VERIFY_TIMEOUT", "10"))
# Billing reports are settlement input, not paid-work gating — a shorter
# budget than the verify call so a slow market cannot stall job completion.
BILLING_TIMEOUT = float(os.environ.get("MARKET_BILLING_TIMEOUT", "5"))

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


async def report_job_billing(
    *,
    job_id: str,
    access_key: str,
    access_secret: str,
    metrics: dict[str, Any],
    final: bool = True,
) -> bool:
    """POST provider-attested billing metrics for a paid job (#2365).

    Called by shop daemons once the job's usage is known. The market
    service stores the metrics and, on ``final``, settles the escrow
    against them — the buyer-side auto-release cannot name a partial
    amount (#1912 relay rule), so this report is the only path to
    metered billing. Never raises: a failed report must not fail paid
    work already delivered; the job then falls back to full-lock
    settlement (or refund at expiry when nothing was attested).
    """

    if not job_id or not access_key or not access_secret or not metrics:
        return False
    try:
        resp = await _verify_client().post(
            f"{MARKET_VERIFY_URL}/v1/market/jobs/{quote(job_id, safe='')}/billing",
            headers={
                "X-Access-Key": access_key,
                "X-Access-Secret": access_secret,
                "X-Job-Id": job_id,
            },
            json={"metrics": metrics, "final": final},
            timeout=BILLING_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 - billing is best-effort; paid work already happened
        logger.warning("billing report for job %s failed: %s", job_id, e)
        return False
    if resp.status_code >= 400:
        logger.warning("billing report for job %s refused: %s %s", job_id, resp.status_code, resp.text[:200])
        return False
    return True


async def report_request_billing(request: Request, metrics: dict[str, Any], *, final: bool = True) -> bool:
    """``report_job_billing`` with the credential triple read off the request.

    The paid route's ``require_job_access`` dependency has already proven
    the triple valid for this job; the daemon replays the same headers on
    the billing POST so the market service binds the report to the serving
    party's job credential.
    """
    try:
        return await report_job_billing(
            job_id=request.headers.get("X-Job-Id", ""),
            access_key=request.headers.get("X-Access-Key", ""),
            access_secret=request.headers.get("X-Access-Secret", ""),
            metrics=metrics,
            final=final,
        )
    except Exception as e:  # noqa: BLE001 - billing is best-effort; paid work already happened
        logger.warning("billing report request failed: %s", e)
        return False


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
