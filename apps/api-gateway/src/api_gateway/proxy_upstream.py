"""Upstream proxy retry + bounded-read machinery — exec'd into ``main.py`` (#1860).

This file is NOT an importable module: ``api_gateway/main.py`` reads it and
``exec``s it in its own globals at the position this code used to occupy.
That keeps every global lookup — including the constants tests monkeypatch
on ``api_gateway.main`` (``UPSTREAM_DEADLINE_SECONDS``,
``MAX_RESPONSE_BYTES``) and the env-derived tables ``importlib.reload``
re-reads — resolving exactly as before the split. The guard makes an
accidental direct import fail loudly instead of double-defining the names.
"""

# ruff: noqa: F821
# (names resolve in api_gateway.main's globals at exec time)

if __name__ == "api_gateway.proxy_upstream":
    raise ImportError("proxy_upstream.py is exec'd by api_gateway.main, not imported")

import asyncio
import re
import time
from typing import TYPE_CHECKING

import httpx
from starlette.datastructures import Headers

if TYPE_CHECKING:
    # Names that live in api_gateway.main's namespace at exec time; imported
    # here only so ruff/mypy resolve them. _upstream_headers is defined by
    # proxy_route.py, exec'd immediately after this file.
    from .main import MAX_RESPONSE_BYTES, SERVICES, UPSTREAM_DEADLINE_SECONDS, _V2_SERVICE_URLS, logger
    from .proxy_route import _upstream_headers


# Errors raised before the request left this process — TCP connect refused,
# connect timeout, pool timeout. Retrying is safe for every method because
# nothing reached upstream.
_UNSENT_REQUEST_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


# APIGW-RETRY-1 (#1667): a client Idempotency-Key alone used to enable
# ambiguous-write retries on EVERY proxied route, but most upstreams do not
# deduplicate the key — a post-send retry could double-apply the write. The
# no-confirm retry path is now an allowlist of (service, upstream-path)
# pairs verified to honor Idempotency-Key dedup. Entries match the UPSTREAM
# path (after the v1 rewrite / v2 verbatim forwarding), not the public
# spelling, so both /v1/... and /api/v2/... routes resolve identically.
# Verified against:
#   coordinator-api contexts/payments/operations.py begin_operation callers
#     (POST /v1/jobs, /v1/jobs/{id}/accept, /v1/payments{,/release,/refund},
#      /v1/escrow/{relay,release,refund}),
#   trading exchange_compat.create_exchange_payment (POST /v1/exchange/create-payment),
#   exchange simple_exchange handlers (_idempotency_key + OperationLedger:
#     POST /api/orders, /api/orders/{id}/cancel, /v1/market/offers[/book]).
# Routes NOT listed — e.g. coordinator job cancel/reject, exchange node
# register/payout, market service writes — get AmbiguousUpstreamError on a
# post-send failure even when the caller sent a key.
_IDEMPOTENT_DEDUP_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("coordinator", re.compile(r"v1/jobs/?$")),
    ("coordinator", re.compile(r"v1/jobs/[^/]+/accept/?$")),
    ("coordinator", re.compile(r"v1/payments/?$")),
    ("coordinator", re.compile(r"v1/payments/[^/]+/(?:release|refund)/?$")),
    ("coordinator", re.compile(r"v1/escrow/(?:relay|release|refund)/?$")),
    ("trading", re.compile(r"v1/exchange/create-payment/?$")),
    ("exchange", re.compile(r"api/orders/?$")),
    ("exchange", re.compile(r"api/orders/[^/]+/cancel/?$")),
    ("exchange", re.compile(r"v1/market/offers/?$")),
    ("exchange", re.compile(r"v1/market/offers/[^/]+/book/?$")),
)


def _upstream_path(service_name: str, target_url: str) -> str:
    """The path portion of ``target_url`` relative to the service's base URL."""
    base = _V2_SERVICE_URLS.get(service_name) or str(SERVICES[service_name]["base_url"])
    if target_url.startswith(base):
        return target_url[len(base) :].lstrip("/")
    return target_url


def _write_retry_is_deduped(service_name: str, upstream_path: str, headers: Headers) -> bool:
    """True when this write may retry ambiguous outcomes: Idempotency-Key
    present AND the upstream route verifiably deduplicates it (#1667)."""
    if "idempotency-key" not in {k.lower() for k in headers.keys()}:
        return False
    path = upstream_path.lstrip("/")
    return any(svc == service_name and pattern.fullmatch(path) for svc, pattern in _IDEMPOTENT_DEDUP_ROUTES)


class AmbiguousUpstreamError(Exception):
    """The upstream may have accepted the request before its response was lost.

    Raised instead of replaying a non-idempotent write; the caller must
    reconcile state (or retry with an Idempotency-Key) rather than risk a
    duplicate side effect.
    """


class _ResponseTooLarge(Exception):
    """Upstream response exceeded GATEWAY_MAX_RESPONSE_BYTES while streaming."""


async def _read_bounded(response: httpx.Response) -> bytes:
    """Read a streamed upstream response under MAX_RESPONSE_BYTES.

    The send used ``stream=True`` so httpx never buffers the body whole; this
    accumulates chunks only up to the cap, then aborts. ``aiter_bytes`` yields
    decoded content, matching what ``response.content`` used to return (the
    gateway strips Accept-Encoding upstream, so identity encoding is expected
    anyway).
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise _ResponseTooLarge(f"upstream response exceeded {MAX_RESPONSE_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def _send_and_read_bounded(
    client: httpx.AsyncClient, request: httpx.Request, deadline: float | None
) -> tuple[httpx.Response, bytes]:
    """One proxied attempt: send + bounded body read under the shared deadline.

    ``deadline`` is a ``time.monotonic()`` timestamp shared across all retry
    attempts (APIGW-RETRY-1, #1667) — ``None`` disables the deadline entirely.
    """
    if deadline is None:
        response = await client.send(request, stream=True)
        try:
            return response, await _read_bounded(response)
        except BaseException:
            # APIGW-OLLAMA-DEPTH2-1 (#1613): on oversize/timeout mid-read the
            # caller never receives `response`, so its finally-aclose can't
            # run — close here or the connection leaks until GC.
            await response.aclose()
            raise
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("upstream deadline exhausted across retries")
    async with asyncio.timeout(remaining):
        response = await client.send(request, stream=True)
        try:
            return response, await _read_bounded(response)
        except BaseException:
            await response.aclose()
            raise


async def proxy_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retry_ambiguous: bool = False,
    headers: dict[str, str] | None = None,
    params: httpx.QueryParams | str | None = None,
    content: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Proxy request with retry logic for transient failures.

    Returns ``(status_code, safe_headers, body)`` — the body is read under
    ``MAX_RESPONSE_BYTES`` before this returns, so the gateway never buffers
    an unbounded upstream response (APIGW-OLLAMA-DEPTH2-1, #1613).

    Pre-send failures are retried for every method. Post-send failures —
    read/write timeouts, mid-stream network errors — are ambiguous: the
    upstream may have committed the request before the response was lost, so
    they are retried only for safe methods or writes whose Idempotency-Key the
    upstream deduplicates. Non-idempotent writes get AmbiguousUpstreamError.

    ``UPSTREAM_DEADLINE_SECONDS`` is a TOTAL deadline across all attempts
    (APIGW-RETRY-1, #1667), not a per-attempt budget — three retries used to
    multiply the worst-case upstream wait by the retry count.
    """
    max_retries = 3
    retry_delay = 0.5
    deadline = time.monotonic() + UPSTREAM_DEADLINE_SECONDS if UPSTREAM_DEADLINE_SECONDS > 0 else None
    for attempt in range(max_retries):
        # stream=True: httpx returns after response headers; the body stays on
        # the wire until _read_bounded pulls it under the cap. Send-level
        # errors still classify exactly as before (nothing reached upstream).
        request = client.build_request(method, url, headers=headers, params=params, content=content)
        response: httpx.Response | None = None
        body = b""
        try:
            response, body = await _send_and_read_bounded(client, request, deadline)
        except _UNSENT_REQUEST_ERRORS:
            if attempt < max_retries - 1:
                logger.warning("Upstream unreachable before send on attempt %s/%s, retrying...", attempt + 1, max_retries)
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            raise
        except httpx.TransportError as exc:
            if not retry_ambiguous:
                raise AmbiguousUpstreamError(url) from exc
            if attempt < max_retries - 1:
                logger.warning("Post-send failure on attempt %s/%s, retrying...", attempt + 1, max_retries)
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            raise
        finally:
            # The stream must be closed however the attempt ended — on success
            # the bounded read already consumed it; on error this releases the
            # connection instead of leaking it until GC.
            if response is not None:
                await response.aclose()
        if response is None:
            raise httpx.RequestError("Max retries exceeded")
        return response.status_code, _upstream_headers(response), body
    raise httpx.RequestError("Max retries exceeded")
