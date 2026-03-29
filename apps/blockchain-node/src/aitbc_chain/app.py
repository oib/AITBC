from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import init_db
from .gossip import create_backend, gossip_broker
from .logger import get_logger
from .mempool import init_mempool
from .metrics import metrics_registry
from .rpc.router import router as rpc_router, set_poa_proposer
from .rpc.websocket import router as websocket_router
# from .escrow_routes import router as escrow_router  # Not yet implemented

_app_logger = get_logger("aitbc_chain.app")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter per client IP."""

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        # Bypass rate limiting for localhost (sync/health internal traffic)
        if client_ip in {"127.0.0.1", "::1"}:
            return await call_next(request)
        now = time.time()
        # Clean old entries
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if now - t < self._window
        ]
        if len(self._requests[client_ip]) >= self._max_requests:
            metrics_registry.increment("rpc_rate_limited_total")
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(self._window)},
            )
        self._requests[client_ip].append(now)
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and error details."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start
            metrics_registry.observe("rpc_request_duration_seconds", duration)
            metrics_registry.increment("rpc_requests_total")
            if response.status_code >= 500:
                metrics_registry.increment("rpc_server_errors_total")
                _app_logger.error("Server error", extra={
                    "method": method, "path": path,
                    "status": response.status_code, "duration_ms": round(duration * 1000, 2),
                })
            elif response.status_code >= 400:
                metrics_registry.increment("rpc_client_errors_total")
            return response
        except Exception as exc:
            duration = time.perf_counter() - start
            metrics_registry.increment("rpc_unhandled_errors_total")
            _app_logger.exception("Unhandled error in request", extra={
                "method": method, "path": path, "error": str(exc),
                "duration_ms": round(duration * 1000, 2),
            })
            return JSONResponse(
                status_code=503,
                content={"detail": "Internal server error"},
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_mempool(
        backend=settings.mempool_backend,
        db_path=str(settings.db_path.parent / "mempool.db"),
        max_size=settings.mempool_max_size,
        min_fee=settings.min_fee,
    )
    backend = create_backend(
        settings.gossip_backend,
        broadcast_url=settings.gossip_broadcast_url,
    )
    await gossip_broker.set_backend(backend)
    
    # Initialize PoA proposer for mining integration
    if settings.enable_block_production and settings.proposer_id:
        try:
            from .consensus import PoAProposer, ProposerConfig
            proposer_config = ProposerConfig(
                chain_id=settings.chain_id,
                proposer_id=settings.proposer_id,
                interval_seconds=settings.block_time_seconds,
                max_block_size_bytes=settings.max_block_size_bytes,
                max_txs_per_block=settings.max_txs_per_block,
            )
            proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
            
            # Set the proposer for mining integration
            set_poa_proposer(proposer)
            
            # Start the proposer if block production is enabled
            asyncio.create_task(proposer.start())
            
            _app_logger.info("PoA proposer initialized for mining integration", extra={
                "proposer_id": settings.proposer_id,
                "chain_id": settings.chain_id
            })
        except Exception as e:
            _app_logger.warning(f"Failed to initialize PoA proposer for mining: {e}")
    
    _app_logger.info("Blockchain node started", extra={"supported_chains": settings.supported_chains})
    try:
        yield
    finally:
        await gossip_broker.shutdown()
        _app_logger.info("Blockchain node stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="AITBC Blockchain Node", version="v0.2.2", lifespan=lifespan)

    # Middleware (applied in reverse order)
    app.add_middleware(RequestLoggingMiddleware)
    # Allow higher RPC throughput (sync + node traffic)
    app.add_middleware(RateLimitMiddleware, max_requests=5000, window_seconds=60)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8000",  # Coordinator API
            "http://localhost:8001",  # Exchange API
            "http://localhost:8002",  # Blockchain Node
            "http://localhost:8003",  # Blockchain RPC
            "http://localhost:8010",  # Multimodal GPU
            "http://localhost:8011",  # GPU Multimodal
            "http://localhost:8012",  # Modality Optimization
            "http://localhost:8013",  # Adaptive Learning
            "http://localhost:8014",  # Marketplace Enhanced
            "http://localhost:8015",  # OpenClaw Enhanced
            "http://localhost:8016",  # Web UI
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(rpc_router, prefix="/rpc", tags=["rpc"])
    app.include_router(websocket_router, prefix="/rpc")
    # app.include_router(escrow_router, prefix="/rpc")  # Disabled until escrow routes are implemented

    # Metrics and health endpoints
    metrics_router = APIRouter()

    @metrics_router.get("/metrics", response_class=PlainTextResponse, tags=["metrics"], summary="Prometheus metrics")
    async def metrics() -> str:
        return metrics_registry.render_prometheus()

    @metrics_router.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict:
        return {
            "status": "ok",
            "supported_chains": [c.strip() for c in settings.supported_chains.split(",") if c.strip()],
            "proposer_id": settings.proposer_id,
        }

    app.include_router(metrics_router)

    return app


app = create_app()
