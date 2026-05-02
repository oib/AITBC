"""
API Gateway main application
Routes requests to microservices
"""

import httpx
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from aitbc import (
    configure_logging,
    get_logger,
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)

# Service registry configuration
SERVICES = {
    "gpu": {
        "base_url": "http://localhost:8101",
        "prefix": "/gpu",
    },
    "marketplace": {
        "base_url": "http://localhost:8102",
        "prefix": "/marketplace",
    },
    "agent": {
        "base_url": "http://localhost:8103",
        "prefix": "/agent",
    },
    "trading": {
        "base_url": "http://localhost:8104",
        "prefix": "/trading",
    },
    "governance": {
        "base_url": "http://localhost:8105",
        "prefix": "/governance",
    },
    "ai": {
        "base_url": "http://localhost:8106",
        "prefix": "/ai",
    },
    "monitoring": {
        "base_url": "http://localhost:8107",
        "prefix": "/monitoring",
    },
    "openclaw": {
        "base_url": "http://localhost:8108",
        "prefix": "/openclaw",
    },
    "plugin": {
        "base_url": "http://localhost:8109",
        "prefix": "/plugin",
    },
    "coordinator": {
        "base_url": "http://localhost:8011",
        "prefix": "/coordinator",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the API Gateway."""
    logger.info("Starting API Gateway")
    yield
    logger.info("Shutting down API Gateway")


app = FastAPI(
    title="AITBC API Gateway",
    description="Routes requests to AITBC microservices",
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10*1024*1024)
app.add_middleware(ErrorHandlerMiddleware)


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


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_request(path: str, request: Request) -> Response:
    """Proxy request to appropriate microservice"""
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
    
    # Proxy the request
    async with httpx.AsyncClient() as client:
        try:
            # Forward headers (except host)
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            
            # Forward the request
            if request.method == "GET":
                response = await client.get(target_url, headers=headers, params=request.query_params)
            elif request.method == "POST":
                body = await request.body()
                response = await client.post(target_url, headers=headers, content=body)
            elif request.method == "PUT":
                body = await request.body()
                response = await client.put(target_url, headers=headers, content=body)
            elif request.method == "DELETE":
                response = await client.delete(target_url, headers=headers)
            elif request.method == "PATCH":
                body = await request.body()
                response = await client.patch(target_url, headers=headers, content=body)
            elif request.method == "OPTIONS":
                response = await client.options(target_url, headers=headers)
            else:
                return JSONResponse(
                    status_code=405,
                    content={"error": "Method not allowed"}
                )
            
            # Return the response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        except httpx.RequestError as e:
            logger.error(
                "Service unavailable",
                service=service_name,
                target_url=target_url,
                error=str(e),
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "type": "service_unavailable",
                        "message": f"Service {service_name} is unavailable",
                        "service": service_name,
                    }
                },
            )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
