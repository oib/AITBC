from aitbc.constants import BLOCKCHAIN_RPC_URL
from typing import Annotated

"""
API Gateway main application
Routes requests to microservices
"""

import asyncio  # noqa: E402
import hmac  # noqa: E402
import os  # noqa: E402
from collections.abc import AsyncIterator, Callable  # noqa: E402
from typing import Any, TypeVar  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
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
COORDINATOR_URL = os.getenv("COORDINATOR_API_URL", "http://localhost:8203")
# Coordinator-owned sub-families of /v1/marketplace — the rest (jobs, offers,
# ratings, ipfs, match, ...) belongs to the marketplace service on :8102.
# The coordinator-owned market sub-routes must be listed before the generic
# "market"/"marketplace" entries: the first prefix match in dict order wins.
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
_MARKET_SERVICE_URL = os.getenv(
    "MARKET_SERVICE_URL",
    os.getenv("MARKETPLACE_SERVICE_URL", "http://localhost:8102"),
)
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
    # Legacy public spellings stay live until their removal is approved; they
    # rewrite to the coordinator's canonical /v1/market/* routes.
    **{
        f"marketplace-{sub}": {
            "base_url": COORDINATOR_URL,
            "prefix": f"/v1/marketplace/{sub}",
            "rewrite": {f"/v1/marketplace/{sub}": f"v1/market/{sub}"},
        }
        for sub in _MARKET_COORDINATOR_PREFIXES
    },
    "market": {
        "base_url": _MARKET_SERVICE_URL,
        "prefix": "/v1/market",
        "rewrite": {"/v1/market": "v1/market"},
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
    "wallet": {
        "base_url": os.getenv("WALLET_SERVICE_URL", "http://localhost:8108"),
        "prefix": "/v1/wallet",
        "rewrite": {"/v1/wallet": "v1"},
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the API Gateway."""
    logger.info("Starting API Gateway")
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    logger.info("Shutting down API Gateway")
    await app.state.http_client.aclose()


app = FastAPI(
    title="AITBC API Gateway", description="Routes requests to AITBC microservices", version="0.1.0", lifespan=lifespan
)
if SLOWAPI_AVAILABLE:
    app.state.limiter = limiter
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
app.add_middleware(ErrorHandlerMiddleware)
if SLOWAPI_AVAILABLE:

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
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


circuit_breaker_state: dict[str, dict[str, object]] = {
    name: {"failures": 0, "last_failure_time": None, "is_open": False} for name in SERVICES
}
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 60


def check_circuit_breaker(service_name: str) -> bool:
    """Check if circuit breaker is open."""
    state = circuit_breaker_state[service_name]
    if state["is_open"]:
        current_time = asyncio.get_event_loop().time()
        last_failure = state["last_failure_time"]
        if last_failure is not None and current_time - last_failure > CIRCUIT_BREAKER_TIMEOUT:  # type: ignore[operator]
            state["is_open"] = False
            state["failures"] = 0
            logger.info("Circuit breaker reset")
            return True
        return False
    return True


def record_failure(service_name: str) -> None:
    """Record a failure for circuit breaker."""
    state = circuit_breaker_state[service_name]
    state["failures"] = (state["failures"] or 0) + 1  # type: ignore[operator]
    state["last_failure_time"] = asyncio.get_event_loop().time()
    if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:  # type: ignore[operator]
        state["is_open"] = True
        logger.warning("Circuit breaker opened")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint"""
    return create_simple_health_response("api-gateway")


@app.get("/services")
async def list_services() -> dict[str, dict[str, object]]:
    """List registered services"""
    return {service_name: {"prefix": config["prefix"], "url": config["base_url"]} for service_name, config in SERVICES.items()}


# Errors raised before the request left this process — TCP connect refused,
# connect timeout, pool timeout. Retrying is safe for every method because
# nothing reached upstream.
_UNSENT_REQUEST_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class AmbiguousUpstreamError(Exception):
    """The upstream may have accepted the request before its response was lost.

    Raised instead of replaying a non-idempotent write; the caller must
    reconcile state (or retry with an Idempotency-Key) rather than risk a
    duplicate side effect.
    """


async def proxy_with_retry(
    client: httpx.AsyncClient, method: str, url: str, *, retry_ambiguous: bool = False, **kwargs: object
) -> httpx.Response:
    """Proxy request with retry logic for transient failures.

    Pre-send failures are retried for every method. Post-send failures —
    read/write timeouts, mid-stream network errors — are ambiguous: the
    upstream may have committed the request before the response was lost, so
    they are retried only for safe methods or writes whose Idempotency-Key the
    upstream deduplicates. Non-idempotent writes get AmbiguousUpstreamError.
    """
    max_retries = 3
    retry_delay = 0.5
    for attempt in range(max_retries):
        try:
            if method == "GET":
                return await client.get(url, **kwargs)  # type: ignore[arg-type]
            elif method == "POST":
                return await client.post(url, **kwargs)  # type: ignore[arg-type]
            elif method == "PUT":
                return await client.put(url, **kwargs)  # type: ignore[arg-type]
            elif method == "DELETE":
                return await client.delete(url, **kwargs)  # type: ignore[arg-type]
            elif method == "PATCH":
                return await client.patch(url, **kwargs)  # type: ignore[arg-type]
            elif method == "OPTIONS":
                return await client.options(url, **kwargs)  # type: ignore[arg-type]
            elif method == "HEAD":
                return await client.head(url, **kwargs)  # type: ignore[arg-type]
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
    raise httpx.RequestError("Max retries exceeded")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@rate_limit(RATE_LIMIT)
async def proxy_request(path: str, request: Request, authenticated: Annotated[bool, Depends(verify_auth)]) -> Response:
    """Proxy request to appropriate microservice with rate limiting and circuit breaker.

    The rate_limit decorator must sit below @app.api_route so slowapi wraps the handler
    before FastAPI registers it. It was previously defined but applied to nothing, so the
    limiter, its 429 handler and app.state.limiter were all wired up while every request
    passed unthrottled.
    """
    service_name: str | None = None
    for name, config in SERVICES.items():
        prefix = config["prefix"].lstrip("/")  # type: ignore
        if path == prefix or path.startswith(prefix + "/"):
            service_name = name
            break
    if not service_name:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": "Not found"})
    if not check_circuit_breaker(service_name):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": f"Circuit breaker is open for {service_name}, service temporarily unavailable"},
        )
    service_config = SERVICES[service_name]
    target_path = path
    prefix = service_config["prefix"].lstrip("/")  # type: ignore
    if "rewrite" in service_config:
        for old_prefix, new_prefix in service_config["rewrite"].items():  # type: ignore
            if target_path.startswith(old_prefix.lstrip("/")):
                remaining_path = target_path[len(old_prefix.lstrip("/")) :]
                target_path = new_prefix.lstrip("/") + remaining_path
                break
    elif path.startswith(prefix):
        target_path = path[len(prefix) :].lstrip("/")
    if target_path.endswith("/"):
        target_path = target_path.rstrip("/")
    target_url = f"{service_config['base_url']}/{target_path}"
    client = app.state.http_client
    try:
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        # Ask upstreams for identity encoding — httpx transparently decodes a
        # gzipped body but the response headers would still claim gzip.
        headers.pop("accept-encoding", None)
        # The gateway credential never leaves this layer.
        headers.pop("x-gateway-key", None)
        if getattr(request.state, "gateway_bearer_auth", False):
            headers.pop("authorization", None)
        # Propagate correlation — the middleware sets state.request_id but does
        # not inject it into the incoming headers.
        headers["x-request-id"] = request.state.request_id
        kwargs: dict[str, object] = {"headers": headers, "params": request.query_params}
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            kwargs["content"] = body
        # Safe methods replay freely. A write replays post-send failures only
        # when it carries an Idempotency-Key the upstream deduplicates.
        retry_ambiguous = request.method in ("GET", "HEAD", "OPTIONS") or "idempotency-key" in request.headers
        response = await proxy_with_retry(client, request.method, target_url, retry_ambiguous=retry_ambiguous, **kwargs)
        # Framing and hop-by-hop headers describe the upstream connection, not
        # this one — forwarding them produces malformed responses (nginx 502).
        upstream_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower()
            not in (
                "content-length",
                "content-encoding",
                "transfer-encoding",
                "connection",
                "keep-alive",
                "server",
                "date",
                "te",
                "trailer",
                "upgrade",
            )
        }
        return Response(content=response.content, status_code=response.status_code, headers=upstream_headers)
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

    uvicorn.run(app, host="0.0.0.0", port=8201, log_level="critical", access_log=False)  # nosec B104 - code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
