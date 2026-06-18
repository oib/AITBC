from typing import Annotated

"""
API Gateway main application
Routes requests to microservices
"""

import asyncio  # noqa: E402
import hmac  # noqa: E402
import os  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
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
configure_logging(level="INFO")
logger = get_logger(__name__)
if SLOWAPI_AVAILABLE:
    limiter: Limiter | None = Limiter(key_func=get_remote_address)
else:
    limiter = None


def rate_limit(limit: str) -> object:
    if limiter is None:
        return lambda func: func
    return limiter.limit(limit)


security = HTTPBearer(auto_error=False)
API_KEY = os.getenv("API_GATEWAY_KEY", "")
REQUIRE_AUTH = os.getenv("API_GATEWAY_REQUIRE_AUTH", "false").lower() == "true"
SERVICES: dict[str, dict[str, object]] = {
    "gpu": {"base_url": os.getenv("GPU_SERVICE_URL", "http://localhost:8101"), "prefix": "/v1/gpu"},
    "marketplace": {"base_url": os.getenv("COORDINATOR_API_URL", "http://localhost:8203"), "prefix": "/v1/marketplace"},
    "hermes": {"base_url": os.getenv("HERMES_SERVICE_URL", "http://localhost:8103"), "prefix": "/v1/hermes"},
    "trading": {"base_url": os.getenv("TRADING_SERVICE_URL", "http://localhost:8104"), "prefix": "/v1/trading"},
    "governance": {"base_url": os.getenv("GOVERNANCE_SERVICE_URL", "http://localhost:8105"), "prefix": "/v1/governance"},
    "exchange": {"base_url": os.getenv("EXCHANGE_SERVICE_URL", "http://localhost:8106"), "prefix": "/v1/exchange"},
    "agent-coordinator": {
        "base_url": os.getenv("AGENT_COORDINATOR_URL", "http://localhost:8107"),
        "prefix": "/v1/agent-coordinator",
    },
    "coordinator": {"base_url": os.getenv("COORDINATOR_API_URL", "http://localhost:8203"), "prefix": "/v1/coordinator"},
    "wallet": {"base_url": os.getenv("WALLET_SERVICE_URL", "http://localhost:8108"), "prefix": "/v1/wallet"},
    "escrow": {"base_url": os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202") + "/rpc", "prefix": "/v1/escrow"},
    "plugin": {
        "base_url": os.getenv("COORDINATOR_API_URL", "http://localhost:8203"),
        "prefix": "/v1/plugin",
        "rewrite": {"/v1/plugin/": "/v1/marketplace/"},
    },
    "ffmpeg": {"base_url": os.getenv("FFMPEG_SERVICE_URL", "http://localhost:8230"), "prefix": "/v1/ffmpeg"},
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


def verify_auth(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> bool:
    """Verify authentication if required."""
    if not REQUIRE_AUTH:
        return True
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication credentials")
    if not API_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API gateway key not configured")
    if not hmac.compare_digest(credentials.credentials, API_KEY):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid authentication credentials")
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
    return {"status": "healthy", "service": "api-gateway"}


@app.get("/services")
async def list_services() -> dict[str, dict[str, object]]:
    """List registered services"""
    return {service_name: {"prefix": config["prefix"], "url": config["base_url"]} for service_name, config in SERVICES.items()}


async def proxy_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs: object) -> httpx.Response:
    """Proxy request with retry logic for transient failures."""
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
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                logger.warning("Timeout on attempt %s/%s, retrying...", attempt + 1, max_retries)
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            raise
        except httpx.ConnectError:
            if attempt < max_retries - 1:
                logger.warning("Connection error on attempt %s/%s, retrying...", attempt + 1, max_retries)
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            raise
    raise httpx.RequestError("Max retries exceeded")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_request(path: str, request: Request, authenticated: Annotated[bool, Depends(verify_auth)]) -> Response:
    """Proxy request to appropriate microservice with rate limiting and circuit breaker."""
    service_name: str | None = None
    for name, config in SERVICES.items():
        if path.startswith(config["prefix"].lstrip("/")):  # type: ignore
            service_name = name
            break
    if not service_name:
        service_name = "coordinator"
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
    elif service_name == "marketplace":
        pass
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
        kwargs: dict[str, object] = {"headers": headers, "params": request.query_params}
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            kwargs["content"] = body
        response = await proxy_with_retry(client, request.method, target_url, **kwargs)
        return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))
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

    uvicorn.run(app, host="0.0.0.0", port=8201)
