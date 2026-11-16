from aitbc.constants import BLOCKCHAIN_RPC_URL
from typing import Annotated

"""
API Gateway main application
Routes requests to microservices
"""

import hmac  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import AsyncIterator, Callable  # noqa: E402
from typing import Any, TypeVar  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

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

# Proxy failure surface: outbound httpx calls to upstreams, request/response
# data-shape errors, and local socket/timeouts — all answered as a 500.
_OPS_ERRORS = (
    httpx.HTTPError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    TimeoutError,
)

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


def _exec_code_fragment(filename: str) -> None:
    """Exec a sibling source fragment in this module's globals (#1860).

    The upstream retry/bounded-read machinery and the proxy route + routing
    helpers moved verbatim into ``proxy_upstream.py`` / ``proxy_route.py``.
    They must keep resolving every global — including the constants tests
    monkeypatch on ``api_gateway.main`` and the env-derived tables
    ``importlib.reload`` re-reads — so they run in this module's own
    namespace rather than a sibling module's. Each fragment carries a guard
    against direct import.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(path, encoding="utf-8") as fragment_file:
        exec(compile(fragment_file.read(), path, "exec"), globals())  # nosec B102


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


# SECRET-RELOAD-1 (#1776): reload JWT/API-key secrets from env files on SIGHUP.
try:
    from aitbc.auth import install_auth_reload_signal as _install_auth_reload_signal
except ImportError:  # aitbc.auth unavailable in minimal test envs
    _install_auth_reload_signal = None  # type: ignore[assignment]
if _install_auth_reload_signal is not None:
    _install_auth_reload_signal()


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


# Upstream retry/bounded-read machinery moved verbatim to
# proxy_upstream.py (#1860 band split); exec'd in this module's namespace —
# see _exec_code_fragment.
_exec_code_fragment("proxy_upstream.py")


# Proxy route + routing/header helpers moved verbatim to proxy_route.py
# (#1860 band split); exec'd in this module's namespace — see
# _exec_code_fragment.
_exec_code_fragment("proxy_route.py")


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
