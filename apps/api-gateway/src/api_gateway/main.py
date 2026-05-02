"""
API Gateway main application
Routes requests to microservices
"""

import os
import httpx
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from aitbc import (
    configure_logging,
    get_logger,
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    logger = get_logger(__name__)
    logger.warning("slowapi not available, rate limiting disabled")

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)

# Rate limiting setup
if SLOWAPI_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address)
else:
    limiter = None

# Authentication setup
security = HTTPBearer(auto_error=False)
API_KEY = os.getenv("API_GATEWAY_KEY", "")
REQUIRE_AUTH = os.getenv("API_GATEWAY_REQUIRE_AUTH", "false").lower() == "true"

# Service registry configuration
SERVICES = {
    "gpu": {
        "base_url": os.getenv("GPU_SERVICE_URL", "http://localhost:8101"),
        "prefix": "/gpu",
    },
    "marketplace": {
        "base_url": os.getenv("MARKETPLACE_SERVICE_URL", "http://localhost:8102"),
        "prefix": "/marketplace",
    },
    "agent": {
        "base_url": os.getenv("AGENT_SERVICE_URL", "http://localhost:8103"),
        "prefix": "/agent",
    },
    "trading": {
        "base_url": os.getenv("TRADING_SERVICE_URL", "http://localhost:8104"),
        "prefix": "/trading",
    },
    "governance": {
        "base_url": os.getenv("GOVERNANCE_SERVICE_URL", "http://localhost:8105"),
        "prefix": "/governance",
    },
    "ai": {
        "base_url": os.getenv("AI_SERVICE_URL", "http://localhost:8106"),
        "prefix": "/ai",
    },
    "monitoring": {
        "base_url": os.getenv("MONITORING_SERVICE_URL", "http://localhost:8107"),
        "prefix": "/monitoring",
    },
    "openclaw": {
        "base_url": os.getenv("OPENCLAW_SERVICE_URL", "http://localhost:8108"),
        "prefix": "/openclaw",
    },
    "plugin": {
        "base_url": os.getenv("PLUGIN_SERVICE_URL", "http://localhost:8109"),
        "prefix": "/plugin",
    },
    "coordinator": {
        "base_url": os.getenv("COORDINATOR_API_URL", "http://localhost:8011"),
        "prefix": "/coordinator",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the API Gateway."""
    logger.info("Starting API Gateway")
    # Create HTTP client with connection pooling and timeout
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    yield
    logger.info("Shutting down API Gateway")
    await app.state.http_client.aclose()


app = FastAPI(
    title="AITBC API Gateway",
    description="Routes requests to AITBC microservices",
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiter if available
if SLOWAPI_AVAILABLE:
    app.state.limiter = limiter

# Add middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10*1024*1024)
app.add_middleware(ErrorHandlerMiddleware)

# Rate limit exception handler
if SLOWAPI_AVAILABLE:
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded", "detail": str(exc)},
        )


# Authentication dependency
def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """Verify authentication if required."""
    if not REQUIRE_AUTH:
        return True
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )
    if not API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API gateway key not configured",
        )
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication credentials",
        )
    return True

# Circuit breaker state
circuit_breaker_state = {
    "failures": 0,
    "last_failure_time": None,
    "is_open": False,
}

CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 60  # seconds


def check_circuit_breaker() -> bool:
    """Check if circuit breaker is open."""
    if circuit_breaker_state["is_open"]:
        # Check if timeout has elapsed
        if (asyncio.get_event_loop().time() - circuit_breaker_state["last_failure_time"]) > CIRCUIT_BREAKER_TIMEOUT:
            circuit_breaker_state["is_open"] = False
            circuit_breaker_state["failures"] = 0
            logger.info("Circuit breaker reset")
            return True
        return False
    return True


def record_failure():
    """Record a failure for circuit breaker."""
    circuit_breaker_state["failures"] += 1
    circuit_breaker_state["last_failure_time"] = asyncio.get_event_loop().time()
    if circuit_breaker_state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        circuit_breaker_state["is_open"] = True
        logger.warning("Circuit breaker opened")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy", "service": "api-gateway"}


@app.get("/services")
async def list_services() -> dict[str, dict[str, str]]:
    """List registered services"""
    return {
        service_name: {"prefix": config["prefix"], "url": config["base_url"]}
        for service_name, config in SERVICES.items()
    }


async def proxy_with_retry(client, method, url, **kwargs):
    """Proxy request with retry logic for transient failures."""
    max_retries = 3
    retry_delay = 0.5  # seconds
    
    for attempt in range(max_retries):
        try:
            if method == "GET":
                return await client.get(url, **kwargs)
            elif method == "POST":
                return await client.post(url, **kwargs)
            elif method == "PUT":
                return await client.put(url, **kwargs)
            elif method == "DELETE":
                return await client.delete(url, **kwargs)
            elif method == "PATCH":
                return await client.patch(url, **kwargs)
            elif method == "OPTIONS":
                return await client.options(url, **kwargs)
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries}, retrying...")
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            raise
        except httpx.ConnectError:
            if attempt < max_retries - 1:
                logger.warning(f"Connection error on attempt {attempt + 1}/{max_retries}, retrying...")
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            raise


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_request(
    path: str,
    request: Request,
    authenticated: bool = Depends(verify_auth),
) -> Response:
    """Proxy request to appropriate microservice with rate limiting and circuit breaker."""
    # Apply rate limiting if available
    if SLOWAPI_AVAILABLE:
        # Rate limit: 100 requests per minute per IP
        limiter.limit("100/minute")(lambda: None)()
    
    # Check circuit breaker
    if not check_circuit_breaker():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Circuit breaker is open, service temporarily unavailable"},
        )
    # Determine which service should handle the request
    service_name = None
    for name, config in SERVICES.items():
        if path.startswith(config["prefix"].lstrip("/")):
            service_name = name
            break
    
    if not service_name:
        # Default to coordinator-api for unknown paths
        service_name = "coordinator"
    
    service_config = SERVICES[service_name]
    
    # Build target URL
    target_path = path
    prefix = service_config["prefix"].lstrip("/")
    if path.startswith(prefix):
        target_path = path[len(prefix):].lstrip("/")
    
    target_url = f"{service_config['base_url']}/{target_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"
    
    # Proxy the request using pooled HTTP client with retry logic
    client = app.state.http_client
    try:
        # Forward headers (except host)
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        
        # Build kwargs for retry function
        kwargs = {"headers": headers, "params": request.query_params}
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            kwargs["content"] = body
        
        # Use retry logic
        response = await proxy_with_retry(client, request.method, target_url, **kwargs)
        
        # Return the response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
    except httpx.RequestError as e:
        logger.error(
            "Service unavailable after retries",
            service=service_name,
            target_url=target_url,
            error=str(e),
        )
        record_failure()
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
    except Exception as e:
        logger.error(
            "Unexpected error in proxy",
            service=service_name,
            error=str(e),
        )
        record_failure()
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "Internal server error",
                }
            },
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)  # nosec B104
