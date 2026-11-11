from aitbc.constants import BLOCKCHAIN_RPC_URL
from typing import Annotated

"""
API Gateway main application
Routes requests to microservices
"""

import asyncio  # noqa: E402
import hmac  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import AsyncIterator, Callable  # noqa: E402
from typing import Any, TypeVar  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.env_compat import market_getenv  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.middleware import (  # noqa: E402
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

    class _DummyLimiter:
        def limit(self, limit: str) -> object:
            return lambda func: func

    def _dummy_get_remote_address(request: Request) -> str:
        return "unknown"

    Limiter = _DummyLimiter  # type: ignore[assignment,misc]
    get_remote_address = _dummy_get_remote_address
configure_logging(level="INFO", service_name="api-gateway", to_file=True)
logger = get_logger(__name__)
if SLOWAPI_AVAILABLE:
    limiter: Limiter | None = Limiter(key_func=get_remote_address)
else:
    limiter = None


_F = TypeVar("_F", bound=Callable[..., Any])


def rate_limit(limit: str) -> Callable[[_F], _F]:
    """Rate-limit decorator, or a no-op when slowapi is unavailable.

    V23-46: this returned ``object``, so ``@rate_limit(...)`` applied a non-callable as far
    as the type checker was concerned -- "object not callable" on the route below, plus a
    ``type: ignore[misc]`` there that was covering for it.
    """
    if limiter is None:
        return lambda func: func
    return limiter.limit(limit)


security = HTTPBearer(auto_error=False)
# Gateway auth lives in X-Gateway-Key, not Authorization: the proxy forwards
# Authorization upstream, where Bearer must remain the service's own credential
# (JWT / peer key). A Bearer carrying the gateway key is still accepted for
# backward compatibility but is stripped before forwarding.
gateway_key_header = APIKeyHeader(name="X-Gateway-Key", auto_error=False)
API_KEY = os.getenv("API_GATEWAY_KEY", "")
REQUIRE_AUTH = os.getenv("API_GATEWAY_REQUIRE_AUTH", "true").lower() == "true"
# Applied to the catch-all proxy route below, which fronts every backend service.
# slowapi syntax, e.g. "100/minute", "20/second".
RATE_LIMIT = os.getenv("API_GATEWAY_RATE_LIMIT", "100/minute")
# Coarse per-IP ceiling evaluated BEFORE verify_auth (GW-RATELIMIT-PRE-AUTH-1,
# #1211): FastAPI resolves dependencies before the slowapi-wrapped handler
# runs, so unauthenticated floods used to 401 inside verify_auth without ever
# reaching the identity-keyed bucket. This dependency is declared ahead of
# `authenticated` on the proxy route so it counts first; authed requests then
# still get the tighter per-identity post-auth bucket. Keyed on the same
# post-realip client address as #1189 — only the local nginx peer may assert
# forwarding headers (uvicorn proxy_headers / forwarded_allow_ips=127.0.0.1).
PREAUTH_RATE_LIMIT = os.getenv("API_GATEWAY_PREAUTH_RATE_LIMIT", "300/minute")
COORDINATOR_URL = os.getenv("COORDINATOR_API_URL", "http://localhost:8203")
# Upstream response bound (APIGW-OLLAMA-DEPTH2-1 / APIGW-DEPTH-1, #1613/#1581):
# the proxy used to hand httpx a non-streaming send, so response.content was
# buffered whole with no ceiling — a huge or drip-fed upstream could hold a
# connection and RAM per in-flight request. The body is now read off the
# stream under GATEWAY_MAX_RESPONSE_BYTES and the whole send+read runs under
# GATEWAY_UPSTREAM_DEADLINE_SECONDS (0 disables the deadline). Both are
# env-tunable; the cap defaults well above the 10 MB request ceiling.
MAX_RESPONSE_BYTES = int(os.getenv("GATEWAY_MAX_RESPONSE_BYTES", str(64 * 1024 * 1024)))
UPSTREAM_DEADLINE_SECONDS = float(os.getenv("GATEWAY_UPSTREAM_DEADLINE_SECONDS", "300"))
# Coordinator-owned sub-families of /v1/market — the rest (jobs, offers,
# ratings, ipfs, match, ...) belongs to the market service on :8102.
# The coordinator-owned market sub-routes must be listed before the generic
# "market" entry: the first prefix match in dict order wins.
_MARKET_COORDINATOR_PREFIXES = (
    "gpu",
    "providers",
    "bonds",
    "miner-offers",
    "native-energy",
    "orders",
    "pricing",
    "sync-offers",
)
_MARKET_SERVICE_URL = market_getenv("MARKET_SERVICE_URL", "http://localhost:8102")
SERVICES: dict[str, dict[str, object]] = {
    "escrow": {
        "base_url": os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL) + "/rpc",
        "prefix": "/v1/escrow",
        # The generic strip drops `v1/escrow`, which would forward to /rpc/create
        # instead of /rpc/escrow/create. Rewrite keeps the escrow segment.
        "rewrite": {"/v1/escrow/": "escrow/"},
    },
    **{
        f"market-{sub}": {
            "base_url": COORDINATOR_URL,
            "prefix": f"/v1/market/{sub}",
            "rewrite": {f"/v1/market/{sub}": f"v1/market/{sub}"},
        }
        for sub in _MARKET_COORDINATOR_PREFIXES
    },
    "market": {
        "base_url": _MARKET_SERVICE_URL,
        "prefix": "/v1/market",
        "rewrite": {"/v1/market": "v1/market"},
    },
    # Pre-rename spelling. The marketplace → market rename promised these
    # aliases and never shipped them, so every caller still on the old paths
    # broke. They mirror the carving above -- and must keep mirroring it, or a
    # coordinator-owned sub-family would land on the market service instead.
    **{
        f"marketplace-{sub}": {
            "base_url": COORDINATOR_URL,
            "prefix": f"/v1/marketplace/{sub}",
            "rewrite": {f"/v1/marketplace/{sub}": f"v1/market/{sub}"},
        }
        for sub in _MARKET_COORDINATOR_PREFIXES
    },
    "marketplace": {
        "base_url": _MARKET_SERVICE_URL,
        "prefix": "/v1/marketplace",
        "rewrite": {"/v1/marketplace": "v1/market"},
    },
    "coordinator": {"base_url": COORDINATOR_URL, "prefix": "/v1/coordinator", "rewrite": {"/v1/coordinator": "v1"}},
    "governance": {
        "base_url": os.getenv("GOVERNANCE_SERVICE_URL", "http://localhost:8105"),
        "prefix": "/v1/governance",
        "rewrite": {"/v1/governance": "v1/governance"},
    },
    "exchange": {
        "base_url": os.getenv("EXCHANGE_SERVICE_URL", "http://localhost:8106"),
        "prefix": "/v1/exchange",
        # The exchange service dispatches legacy /api/* paths internally.
        "rewrite": {"/v1/exchange": "api"},
    },
    "trading": {
        "base_url": os.getenv("TRADING_SERVICE_URL", "http://localhost:8104"),
        "prefix": "/v1/trading",
        # Trading serves /v1/exchange/*, /v1/blocks, /v1/explorer — alias to its v1 root.
        "rewrite": {"/v1/trading": "v1"},
    },
    "agent-coordinator": {
        "base_url": os.getenv("AGENT_COORDINATOR_URL", "http://localhost:8107"),
        "prefix": "/v1/agent-coordinator",
        "rewrite": {"/v1/agent-coordinator": "v1"},
    },
    # Agent-coordinator's internal message/auth surface lives at /api/v1/agent/*.
    "agent": {
        "base_url": os.getenv("AGENT_COORDINATOR_URL", "http://localhost:8107"),
        "prefix": "/v1/agent",
        "rewrite": {"/v1/agent": "api/v1/agent"},
    },
    "pool-hub": {
        "base_url": os.getenv("POOL_HUB_URL", "http://localhost:8210"),
        "prefix": "/v1/pool-hub",
        "rewrite": {"/v1/pool-hub": "v1"},
    },
    "explorer": {
        "base_url": os.getenv("EXPLORER_SERVICE_URL", "http://localhost:8100"),
        "prefix": "/v1/explorer",
        # The explorer serves /api/* paths.
        "rewrite": {"/v1/explorer": "api"},
    },
    "plugin": {
        "base_url": COORDINATOR_URL,
        "prefix": "/v1/plugin",
        "rewrite": {"/v1/plugin/": "/v1/market/"},
    },
}


# ── /api/v2 service-qualified surface ────────────────────────────────────────
#
# Public shape: /api/v2/<service>/<upstream path>. The qualifier selects the
# upstream; everything after it is forwarded verbatim. v1's prefix table above
# cannot express that — /v1/market is carved up between the market service and
# coordinator-owned sub-families — so v2 does not reuse it. Here /api/v2/market/v1/market/gpu goes to the market
# service (which answers 404 for a route it does not own) and the coordinator's
# copy lives honestly at /api/v2/coordinator/v1/market/gpu.
#
# The table below deliberately excludes: the coordinator sub-prefix entries
# (v1 collision artifacts), "plugin" (a rewrite alias), "marketplace" (a legacy
# spelling kept for v1 only), and "escrow" (a route family on the chain node,
# reachable as /api/v2/chain/rpc/escrow/*).
_V2_SERVICE_ENV: dict[str, str] = {
    "market": "MARKET_SERVICE_URL",
    "coordinator": "COORDINATOR_URL",
    "governance": "GOVERNANCE_SERVICE_URL",
    "exchange": "EXCHANGE_SERVICE_URL",
    "trading": "TRADING_SERVICE_URL",
    "agent-coordinator": "AGENT_COORDINATOR_URL",
    "pool-hub": "POOL_HUB_URL",
    "explorer": "EXPLORER_SERVICE_URL",
    "chain": "BLOCKCHAIN_RPC_URL",
}
# Base URLs come out of the SERVICES table so one env override moves both
# spellings; "chain" has no v1 entry and reads the node URL directly.
_V2_SERVICE_URLS: dict[str, str] = {name: str(SERVICES[name]["base_url"]) for name in _V2_SERVICE_ENV if name != "chain"}
_V2_SERVICE_URLS["chain"] = os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the API Gateway."""
    logger.info("Starting API Gateway")
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    logger.info("Shutting down API Gateway")
    client = getattr(app.state, "http_client", None)
    if client is not None:
        await client.aclose()


app = FastAPI(
    title="AITBC API Gateway",
    description="Routes requests to AITBC microservices",
    version="0.1.0",
    lifespan=lifespan,
    # APIGW-DEPTH-1 (#1581): the interactive docs and the OpenAPI schema are
    # unauthenticated meta surface — /docs, /redoc and /openapi.json disclosed
    # the full route table to anonymous callers. The schema is still generated
    # on demand for scripts/extract_openapi_specs.py via app.openapi().
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
if SLOWAPI_AVAILABLE:
    app.state.limiter = limiter
# The gateway is the trust edge: a client-supplied X-Request-ID is forged
# correlation + log/response injection, so inbound ids are not honored here.
# Upstream services keep the middleware default (trust the gateway's stamp).
app.add_middleware(RequestIDMiddleware, trust_inbound=False)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
app.add_middleware(ErrorHandlerMiddleware)
if SLOWAPI_AVAILABLE:

    @app.exception_handler(RateLimitExceeded)
    def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"error": "Rate limit exceeded", "detail": str(exc)}
        )


def verify_auth(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> bool:
    """Verify gateway authentication (X-Gateway-Key, or Bearer as a legacy alias)."""
    if not REQUIRE_AUTH:
        return True
    gateway_key = request.headers.get("X-Gateway-Key")
    bearer = credentials.credentials if credentials else None
    if not gateway_key and not bearer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication credentials")
    if not API_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API gateway key not configured")
    if not hmac.compare_digest(gateway_key or bearer or "", API_KEY):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid authentication credentials")
    # Bearer carried the gateway credential, not a service token — do not leak it upstream.
    request.state.gateway_bearer_auth = not gateway_key and bool(bearer)
    return True


class _PreAuthIpLimiter:
    """Fixed-window per-IP counter for the pre-auth bucket.

    In-memory per process — the same tradeoff slowapi's default storage
    makes. Windows are keyed on the post-realip client address.
    """

    _PERIODS = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}
    _MAX_KEYS = 100_000

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    @classmethod
    def _parse(cls, spec: str) -> tuple[int, float]:
        count_text, _, period_text = spec.partition("/")
        unit = period_text.strip().lower().rstrip("s") or "minute"
        limit = int(count_text)
        if limit <= 0:
            raise ValueError(f"non-positive rate limit in {spec!r}")
        return limit, cls._PERIODS.get(unit, 60.0)

    def check(self, key: str, spec: str) -> bool:
        """Record one hit for ``key``; return False when over ``spec``.

        A malformed spec must not raise inside the per-request dependency —
        that used to 500 every proxied call when the env value was bad
        (APIGW-DEPTH-1 residual, #1581). Fall back to a conservative
        60/minute; the env value itself is validated once at startup below.
        """
        try:
            limit, period = self._parse(spec)
        except (TypeError, ValueError):
            limit, period = 60, 60.0
        now = time.monotonic()
        with self._lock:
            if len(self._windows) > self._MAX_KEYS:
                self._windows = {k: v for k, v in self._windows.items() if now - v[0] < period}
            start, count = self._windows.get(key, (now, 0))
            if now - start >= period:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
        return count <= limit


_PREAUTH_LIMITER = _PreAuthIpLimiter()

# Validate the configured spec once at startup so a malformed
# API_GATEWAY_PREAUTH_RATE_LIMIT shows up in the boot log instead of only
# as per-request fallback warnings (APIGW-DEPTH-1, #1581).
try:
    _PreAuthIpLimiter._parse(PREAUTH_RATE_LIMIT)
except (TypeError, ValueError):
    logger.error(
        "Invalid API_GATEWAY_PREAUTH_RATE_LIMIT %r — falling back to '60/minute'",
        PREAUTH_RATE_LIMIT,
    )
    PREAUTH_RATE_LIMIT = "60/minute"


def pre_auth_ip_limit(request: Request) -> None:
    """Coarse per-IP rate limit evaluated before gateway auth.

    Unauthenticated floods used to 401 inside ``verify_auth`` without ever
    reaching the slowapi limiter — FastAPI resolves dependencies before the
    wrapped handler runs. Declared before ``authenticated`` on the proxy
    route so this bucket counts first; the identity-keyed post-auth bucket
    is unchanged.
    """
    key = request.client.host if request.client else "unknown"
    if not _PREAUTH_LIMITER.check(key, PREAUTH_RATE_LIMIT):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")


# Opt-in: count completed upstream 5xx responses toward the breaker, not just
# transport failures (APIGW-DEPTH-1 residual, #1581). Off by default — a
# service that legitimately answers 5xx on some routes must not trip the
# breaker on sporadic errors; enable per deployment when upstream 5xx means
# "down".
BREAKER_COUNT_5XX = os.getenv("GATEWAY_BREAKER_COUNT_5XX", "false").lower() in ("1", "true", "yes")

circuit_breaker_state: dict[str, dict[str, object]] = {
    name: {"failures": 0, "last_failure_time": None, "is_open": False, "probe_in_flight": False}
    for name in (*SERVICES, *_V2_SERVICE_URLS)
}
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 60


def check_circuit_breaker(service_name: str) -> bool:
    """Check if circuit breaker is open.

    Half-open (APIGW-DEPTH-1, #1581): after the timeout the breaker admits a
    SINGLE probe request instead of resetting outright — the old code let the
    whole traffic flood back at once (thundering herd) and a still-sick
    upstream re-opened only after another full threshold of failures. The
    probe's outcome is settled by note_upstream_response/record_failure.
    Monotonic clock: loop.time() is also monotonic but get_event_loop() is
    deprecated in this context.
    """
    state = circuit_breaker_state[service_name]
    if state["is_open"]:
        last_failure = state["last_failure_time"]
        if (
            last_failure is not None and time.monotonic() - last_failure > CIRCUIT_BREAKER_TIMEOUT  # type: ignore[operator]
        ):
            if state["probe_in_flight"]:
                return False
            state["probe_in_flight"] = True
            return True
        return False
    return True


def record_failure(service_name: str) -> None:
    """Record a failure for circuit breaker."""
    state = circuit_breaker_state[service_name]
    state["probe_in_flight"] = False
    state["failures"] = (state["failures"] or 0) + 1  # type: ignore[operator]
    state["last_failure_time"] = time.monotonic()
    if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:  # type: ignore[operator]
        state["is_open"] = True
        logger.warning("Circuit breaker opened")


def note_upstream_response(service_name: str, status_code: int) -> None:
    """Settle breaker state once an upstream response has been received.

    A half-open probe that got any HTTP response proves the upstream is
    reachable: <500 closes the breaker, >=500 re-opens it immediately. For
    non-probe traffic a 5xx counts as a failure only when the operator opted
    in via GATEWAY_BREAKER_COUNT_5XX; any <500 response forgives sporadic
    failures so the counter cannot grow forever on a recovered service
    (GW-CIRCUIT-1, #1428).
    """
    state = circuit_breaker_state[service_name]
    if state["probe_in_flight"]:
        state["probe_in_flight"] = False
        if status_code < 500:
            state["is_open"] = False
            state["failures"] = 0
            state["last_failure_time"] = None
            logger.info("Circuit breaker closed by half-open probe")
        else:
            record_failure(service_name)
        return
    if BREAKER_COUNT_5XX and status_code >= 500:
        record_failure(service_name)
    elif status_code < 500:
        state["failures"] = 0
        state["last_failure_time"] = None


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint"""
    return create_simple_health_response("api-gateway")


@app.get("/services", dependencies=[Depends(verify_auth)])
def list_services() -> dict[str, dict[str, object]]:
    """List registered services"""
    return {service_name: {"prefix": config["prefix"], "url": config["base_url"]} for service_name, config in SERVICES.items()}


@app.get("/v2", dependencies=[Depends(verify_auth)])
def api_v2_index() -> dict[str, object]:
    """The service-qualified API surface.

    Reached publicly as /api/v2 (nginx mounts the gateway at /api/). Each
    qualifier forwards the remainder of the path to its upstream verbatim;
    docs/api/api-v2-map.json is the generated route map for this table.
    """
    return {
        "api": "v2",
        "rule": "/api/v2/<service>/<upstream path> forwards <upstream path> to the service verbatim",
        "services": {
            name: {"prefix": f"/api/v2/{name}", "url": url, "env": _V2_SERVICE_ENV[name]}
            for name, url in sorted(_V2_SERVICE_URLS.items())
        },
    }


@app.get("/ready", dependencies=[Depends(verify_auth)])
async def ready() -> Response:
    """Readiness probe — 503 while an enabled required feature is unavailable.

    A proxy is not unready because one upstream is: its other routes still
    work and the circuit breaker already reports the broken one. The required
    surface is therefore just the proxy client, plus whatever upstreams the
    operator explicitly declared in GATEWAY_REQUIRED_SERVICES (service names
    from /services or v2 qualifiers; an unrecognized name fails the check —
    a typo'd requirement must not silently pass).
    """
    if getattr(app.state, "http_client", None) is None:
        logger.error("Readiness check failed: http_client")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "api-gateway",
                "error": "readiness check failed",
                "failed": ["http_client"],
            },
        )
    required = [s.strip() for s in os.getenv("GATEWAY_REQUIRED_SERVICES", "").split(",") if s.strip()]
    upstreams: dict[str, str] = {name: str(cfg["base_url"]) for name, cfg in SERVICES.items()}
    upstreams.update(_V2_SERVICE_URLS)
    failed: list[str] = []
    for name in required:
        base = upstreams.get(name)
        if base is None:
            logger.error("GATEWAY_REQUIRED_SERVICES names unknown service: %s", name)
            failed.append(name)
            continue
        try:
            resp = await app.state.http_client.get(f"{base}/health", timeout=3.0)
            if resp.status_code >= 400:
                failed.append(name)
        except Exception:
            logger.exception("Readiness check failed for required service: %s", name)
            failed.append(name)
    if failed:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "api-gateway", "error": "readiness check failed", "failed": failed},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "service": "api-gateway", "required": required},
    )


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
    except Exception:
        logger.error("Unexpected error in proxy")
        record_failure(service_name)
        return JSONResponse(status_code=500, content={"error": {"type": "internal_error", "message": "Internal server error"}})


if __name__ == "__main__":
    import uvicorn

    # code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
    # proxy_headers matches the unit: only localhost peers (nginx) may assert
    # client identity, so the rate limiter keys on the post-realip address.
    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104
        port=8201,
        log_level="critical",
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
