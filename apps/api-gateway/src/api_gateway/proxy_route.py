"""Proxy route + routing/header helpers — exec'd into ``main.py`` (#1860).

Same contract as ``proxy_upstream.py``: ``api_gateway/main.py`` execs this
file in its own globals where the code used to sit, so route registration
order on ``app``, the ``Depends``/``rate_limit`` wiring evaluated at def
time, and every monkeypatch/reload seam on ``api_gateway.main`` are
unchanged. Not importable directly — see the guard.
"""

# ruff: noqa: F821
# (names resolve in api_gateway.main's globals at exec time)

if __name__ == "api_gateway.proxy_route":
    raise ImportError("proxy_route.py is exec'd by api_gateway.main, not imported")

from typing import TYPE_CHECKING, Annotated

import httpx
from fastapi import Depends, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers

if TYPE_CHECKING:
    # Names that live in api_gateway.main's namespace at exec time; imported
    # here only so ruff/mypy resolve them. The retry/routing helpers come
    # from proxy_upstream.py, exec'd immediately before this file.
    from .main import (
        RATE_LIMIT,
        SERVICES,
        _OPS_ERRORS,
        _V2_SERVICE_URLS,
        app,
        check_circuit_breaker,
        logger,
        note_upstream_response,
        pre_auth_ip_limit,
        rate_limit,
        record_failure,
        verify_auth,
    )
    from .proxy_upstream import (
        AmbiguousUpstreamError,
        _ResponseTooLarge,
        _upstream_path,
        _write_retry_is_deduped,
        proxy_with_retry,
    )


def _resolve_target(path: str) -> tuple[str, str] | JSONResponse:
    """Resolve an incoming path to ``(service name, upstream URL)``.

    ``v2/`` paths are service-qualified: the qualifier picks the upstream and
    the rest goes verbatim. Everything else goes through the v1 prefix table.
    Returns a JSONResponse (404) when nothing claims the path.
    """
    # Dot-segment traversal (APIGW-DEPTH-1 residual, #1581): `..` survives the
    # prefix checks and httpx normalizes it into the upstream URL, resolving a
    # different path than the matched prefix implied. No auth bypass is known
    # — upstream auth still applies — but no legitimate client sends dot
    # segments through the gateway, so reject them outright (covers the v1
    # table and the verbatim v2 path alike; %2e decodes to '.' upstream of
    # this function via the path parameter).
    if any(seg in (".", "..") for seg in path.split("/")):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid path"})
    if path.startswith("v2/"):
        # Service-qualified surface (publicly /api/v2/<service>/<path>): the
        # qualifier picks the upstream and the rest of the path goes verbatim —
        # no rewrites, no sub-prefix carving, so nothing here can collide with
        # the v1 table.
        qualifier, _, upstream_path = path[len("v2/") :].partition("/")
        base = _V2_SERVICE_URLS.get(qualifier)
        if base is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"Unknown /api/v2 service: {qualifier}"},
            )
        if not upstream_path:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": f"/api/v2/{qualifier} requires an upstream path"},
            )
        return qualifier, f"{base}/{upstream_path}"
    resolved = resolve_v1_route(path)
    if resolved is not None:
        return resolved
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "Not found"})


# Client-asserted forwarding metadata the edge must never pass through
# (APIGW-HEADER-TRUST-2, #1681): upstreams honor Forwarded / X-Forwarded-Host
# / X-Forwarded-Proto when building URLs and scheme decisions, so a verbatim
# client value steers those responses. X-Forwarded-For / X-Real-IP are handled
# separately — overwritten from the observed peer, never forwarded.
#
# #1753: X-Forwarded-Prefix joined the set — coordinator-api's media upload
# embeds it verbatim into the returned download_url, so a forged value made
# the service emit attacker-controlled URL prefixes. The edge nginx sets
# X-Forwarded-Prefix only on the /c/* locations that proxy DIRECTLY to
# coordinator-api (legacy failover, bypassing this gateway); nothing in the
# /api/ -> gateway path legitimately supplies it, and the gateway does no
# path-prefix routing of its own, so there is no trusted value to preserve.
# The remaining entries (path/uri/script-name/ssl/protocol) are the standard
# companions no upstream reads today but none should ever cross the edge
# either.
_UNTRUSTED_FORWARDING_HEADERS = frozenset(
    {
        "forwarded",
        "x-forwarded",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-port",
        "x-forwarded-server",
        "x-forwarded-scheme",
        "x-forwarded-prefix",
        "x-forwarded-path",
        "x-forwarded-uri",
        "x-forwarded-ssl",
        "x-forwarded-protocol",
        "x-script-name",
        "x-original-url",
        "x-original-host",
        "x-original-proto",
        "x-rewrite-url",
        "x-host",
    }
)


# RFC 7230 §6.1 hop-by-hop headers — connection-specific, never forwarded.
# Anything the Connection header nominates joins this set per-request.
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def _strip_hop_by_hop(headers: Headers) -> dict[str, str]:
    """Drop hop-by-hop headers plus any header names Connection nominates.

    Takes the multi-dict, not a collapsed dict: duplicate ``Connection``
    headers each nominate their own tokens, and ``dict(headers)`` would
    keep only the first value.
    """
    nominated = {
        token.strip().lower() for value in headers.getlist("connection") for token in value.split(",") if token.strip()
    }
    drop = _HOP_BY_HOP_HEADERS | nominated
    return {k: v for k, v in headers.items() if k.lower() not in drop}


def _stamp_forwarding_headers(headers: dict[str, str], request: Request) -> None:
    """Set the caller's identity on the headers sent upstream, in place.

    ``X-Real-IP`` is overwritten with the address this gateway observed
    (``request.client.host`` — the TCP peer, or the real client when
    uvicorn's trusted-peer ``--proxy-headers`` handling already resolved it
    from the edge nginx). ``X-Forwarded-For`` is overwritten with that same
    address: the client-supplied chain is dropped entirely rather than
    appended to, so no spoofed entry ever reaches the upstream (#1177 —
    operator ruling: overwrite, never append/forward verbatim). A
    client-supplied value of either header is never forwarded as is, which
    is what let a caller pick its own upstream rate-limit identity.
    """
    for name in [k for k in headers if k.lower() in ("x-real-ip", "x-forwarded-for")]:
        del headers[name]
    peer = request.client.host if request.client else ""
    if not peer:
        return
    headers["x-real-ip"] = peer
    headers["x-forwarded-for"] = peer


def _strip_client_forwarding_headers(headers: dict[str, str]) -> None:
    """Drop client-asserted Forwarded/X-Forwarded-* metadata in place (#1681)."""
    for name in [k for k in headers if k.lower() in _UNTRUSTED_FORWARDING_HEADERS]:
        del headers[name]


def _upstream_headers(response: httpx.Response) -> dict[str, str]:
    """Response headers safe to forward to the client.

    Framing and hop-by-hop headers describe the upstream connection, not
    this one — forwarding them produces malformed responses (nginx 502).
    """
    hop_by_hop = _HOP_BY_HOP_HEADERS | {"content-length", "content-encoding", "server", "date"}
    return {k: v for k, v in response.headers.items() if k.lower() not in hop_by_hop}


def resolve_v1_route(path: str) -> tuple[str, str] | None:
    """Map a v1 request path to its ``(service name, upstream URL)``.

    ``path`` carries no leading slash, the way FastAPI's catch-all hands it over.
    The first prefix in ``SERVICES`` order that claims the path wins, which is what
    keeps the coordinator-owned sub-families ahead of the generic market entry.
    Returns None when nothing claims it.
    """
    for name, config in SERVICES.items():
        prefix = str(config["prefix"]).lstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            matched = name
            break
    else:
        return None

    target_path = path
    rewrite = config.get("rewrite")
    if isinstance(rewrite, dict):
        for old_prefix, new_prefix in rewrite.items():
            old = str(old_prefix).lstrip("/")
            if target_path.startswith(old):
                target_path = str(new_prefix).lstrip("/") + target_path[len(old) :]
                break
    elif path.startswith(prefix):
        target_path = path[len(prefix) :].lstrip("/")
    if target_path.endswith("/"):
        target_path = target_path.rstrip("/")
    return matched, f"{config['base_url']}/{target_path}"


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@rate_limit(RATE_LIMIT)
async def proxy_request(
    path: str,
    request: Request,
    _pre_auth: Annotated[None, Depends(pre_auth_ip_limit)],
    authenticated: Annotated[bool, Depends(verify_auth)],
) -> Response:
    """Proxy request to appropriate microservice with rate limiting and circuit breaker.

    The rate_limit decorator must sit below @app.api_route so slowapi wraps the handler
    before FastAPI registers it. It was previously defined but applied to nothing, so the
    limiter, its 429 handler and app.state.limiter were all wired up while every request
    passed unthrottled.

    ``_pre_auth`` is declared before ``authenticated`` deliberately: FastAPI solves
    dependencies in signature order, so the per-IP pre-auth bucket counts the request
    before ``verify_auth`` can 401 it — the gap B's live-tier probe found (#1211).
    """
    resolved = _resolve_target(path)
    if isinstance(resolved, JSONResponse):
        return resolved
    service_name, target_url = resolved
    if not check_circuit_breaker(service_name):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": f"Circuit breaker is open for {service_name}, service temporarily unavailable"},
        )
    client = app.state.http_client
    try:
        # Hop-by-hop headers (TE/CL, Connection, Upgrade, ...) describe this
        # connection, not the upstream one — forwarding them verbatim made
        # httpx emit a TE+CL conflict and every chunked /api/ request 400.
        # PI-API-006.
        headers = _strip_hop_by_hop(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        # Client-asserted Forwarded/X-Forwarded-* metadata is dropped at the
        # edge — upstreams that honor it would otherwise take URL/scheme
        # decisions from whatever the caller wrote (#1681).
        _strip_client_forwarding_headers(headers)
        # Ask upstreams for identity encoding — httpx transparently decodes a
        # gzipped body but the response headers would still claim gzip.
        headers.pop("accept-encoding", None)
        # The gateway credential never leaves this layer.
        headers.pop("x-gateway-key", None)
        # Caller identity for the upstream rate limits comes from this hop's
        # own observation, never from what the client wrote (#1244).
        _stamp_forwarding_headers(headers, request)
        if getattr(request.state, "gateway_bearer_auth", False):
            headers.pop("authorization", None)
        # Propagate correlation — the middleware sets state.request_id but does
        # not inject it into the incoming headers.
        headers["x-request-id"] = request.state.request_id
        body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
        # Safe methods replay freely. A write replays post-send failures only
        # when it carries an Idempotency-Key AND the upstream route verifiably
        # deduplicates it — a bare client key is not proof of upstream dedup
        # (APIGW-RETRY-1, #1667).
        retry_ambiguous = request.method in ("GET", "HEAD", "OPTIONS") or _write_retry_is_deduped(
            service_name, _upstream_path(service_name, target_url), request.headers
        )
        upstream_status, upstream_headers, upstream_body = await proxy_with_retry(
            client,
            request.method,
            target_url,
            retry_ambiguous=retry_ambiguous,
            headers=headers,
            # Raw query string keeps repeated params verbatim (#1425 semantics)
            # and satisfies httpx's params type without a starlette->httpx cast.
            params=request.url.query,
            content=body,
        )
        # Any HTTP response — including a half-open probe's — settles the
        # breaker before the body is handed to the client.
        note_upstream_response(service_name, upstream_status)
        return Response(content=upstream_body, status_code=upstream_status, headers=upstream_headers)
    except _ResponseTooLarge:
        logger.error("Upstream response over cap for %s %s", request.method, target_url)
        record_failure(service_name)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {"type": "upstream_response_too_large", "message": "Upstream response exceeded the gateway size cap"}
            },
        )
    except TimeoutError:
        # GATEWAY_UPSTREAM_DEADLINE_SECONDS elapsed mid send/read — the
        # upstream may have committed the request, so this is the same
        # outcome-unknown class as AmbiguousUpstreamError.
        logger.error("Upstream deadline exceeded for %s %s", request.method, target_url)
        record_failure(service_name)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "type": "outcome_unknown",
                    "message": "The upstream did not answer within the gateway deadline; "
                    "the request may have been accepted. Reconcile or retry with an Idempotency-Key.",
                    "service": service_name,
                }
            },
        )
    except AmbiguousUpstreamError:
        logger.error(
            "Ambiguous outcome for %s %s: upstream may have accepted it; not retried without Idempotency-Key",
            request.method,
            target_url,
        )
        record_failure(service_name)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "type": "outcome_unknown",
                    "message": "The upstream may have accepted this request before its response was lost. "
                    "Reconcile the operation or retry with an Idempotency-Key.",
                    "service": service_name,
                }
            },
        )
    except httpx.RequestError:
        logger.error("Service unavailable after retries")
        record_failure(service_name)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "type": "service_unavailable",
                    "message": f"Service {service_name} is unavailable after retries",
                    "service": service_name,
                }
            },
        )
    except _OPS_ERRORS:
        logger.error("Unexpected error in proxy")
        record_failure(service_name)
        return JSONResponse(status_code=500, content={"error": {"type": "internal_error", "message": "Internal server error"}})
