from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from aitbc.middleware import setup_cors
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import init_db, session_scope
from .gossip import create_backend, gossip_broker
from .lease_tracker import lease_tracker
from .logger import get_logger
from .mempool import init_mempool
from .metrics import metrics_registry
from .network.island_manager import create_island_manager
from .rpc.escrow_routes import router as escrow_router
from .rpc.router import router as rpc_router
from .rpc.utils import set_poa_proposer
from .rpc.websocket import router as websocket_router

from aitbc.aitbc_logging import configure_logging
from aitbc.async_tasks import create_task_with_logging

marketplace_router: APIRouter | None
try:
    from .rpc.marketplace import router as marketplace_router
except ImportError:
    marketplace_router = None
_app_logger = get_logger("aitbc_chain.app")


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit requests by client IP."""

    def __init__(self, app: Any, max_requests: int = 1000, window_seconds: int = 60) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < self._window]
        if len(self._requests[client_ip]) >= self._max_requests:
            metrics_registry.increment("rpc_rate_limited_total")
            return JSONResponse(
                status_code=429, content={"detail": "Rate limit exceeded"}, headers={"Retry-After": str(self._window)}
            )
        self._requests[client_ip].append(now)
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and error details."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        query = request.url.query
        path_with_qs = f"{path}?{query}" if query else path
        client_host = request.client.host if request.client else "unknown"
        x_forwarded = request.headers.get("x-forwarded-for", "")
        if x_forwarded:
            client_host = x_forwarded.split(",")[0].strip() or client_host
        user_agent = request.headers.get("user-agent", "unknown")
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start
            metrics_registry.observe("rpc_request_duration_seconds", duration)
            metrics_registry.increment("rpc_requests_total")
            if response.status_code >= 500:
                metrics_registry.increment("rpc_server_errors_total")
                _app_logger.error(
                    "Server error: %s %s from %s (UA: %s) → %d (%.1fms)",
                    method,
                    path_with_qs,
                    client_host,
                    user_agent,
                    response.status_code,
                    duration * 1000,
                )
            elif response.status_code >= 400:
                metrics_registry.increment("rpc_client_errors_total")
                _app_logger.warning(
                    "Client error: %s %s from %s (UA: %s) → %d (%.1fms)",
                    method,
                    path_with_qs,
                    client_host,
                    user_agent,
                    response.status_code,
                    duration * 1000,
                )
            return response
        except HTTPException:
            raise
        except Exception as exc:
            duration = time.perf_counter() - start
            metrics_registry.increment("rpc_unhandled_errors_total")
            _app_logger.exception(
                f"Unhandled error in request: {method} {path_with_qs} from {client_host} (UA: {user_agent})",
                extra={
                    "method": method,
                    "path": path_with_qs,
                    "client_host": client_host,
                    "user_agent": user_agent,
                    "error": str(exc),
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            return JSONResponse(status_code=503, content={"detail": f"Internal server error: {str(exc)}"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    from .contracts.escrow import create_escrow_manager

    escrow_manager = create_escrow_manager()
    await escrow_manager.load_from_db()
    init_mempool(
        backend=settings.mempool_backend,
        db_url=settings.mempool_db_url,
        max_size=settings.mempool_max_size,
        min_fee=settings.min_fee,
    )
    _app_logger.info("Initializing gossip backend: %s, url: %s", settings.gossip_backend, settings.gossip_broadcast_url)
    _backend = create_backend(
        settings.gossip_backend,
        broadcast_url=settings.gossip_broadcast_url,
        websocket_url=settings.gossip_websocket_url,
        mesh_peer_urls=settings.mesh_peer_url_list(),
    )
    await gossip_broker.set_backend(_backend)

    try:
        node_id = os.getenv("NODE_ID", "unknown-node")
        default_island_id = os.getenv(
            "DEFAULT_ISLAND_ID",
            f"{settings.supported_chains.split(',')[0].strip() or settings.chain_id}-island",
        )
        default_chain_id = settings.supported_chains.split(",")[0].strip() or settings.chain_id or "ait-mainnet"
        create_island_manager(node_id, default_island_id, default_chain_id)
    except Exception as e:
        _app_logger.error("Failed to initialize island manager: %s", e)

    # v0.6.4: Initialize MultiChainManager in the RPC service so that
    # /rpc/chains and /rpc/chains/start|stop endpoints work without the
    # separate blockchain-node service process.
    try:
        from .network.multi_chain_manager import create_multi_chain_manager

        _mcm_chain_id = locals().get("default_chain_id") or settings.chain_id or "ait-mainnet"
        base_db_path = Path(settings.get_db_path(_mcm_chain_id))
        create_multi_chain_manager(
            default_chain_id=_mcm_chain_id,
            base_db_path=base_db_path,
            base_rpc_port=int(os.getenv("RPC_PORT", "8202")),
            base_p2p_port=int(os.getenv("P2P_PORT", "8200")),
        )
        _app_logger.info("Multi-chain manager initialized in RPC service")
    except Exception as e:
        _app_logger.warning("Failed to initialize multi-chain manager: %s", e)

    proposers = []
    block_production_override = _env_value(
        "AITBC_FORCE_ENABLE_BLOCK_PRODUCTION", "ENABLE_BLOCK_PRODUCTION", "enable_block_production"
    )
    block_production_enabled = settings.enable_block_production
    if block_production_override is not None:
        block_production_enabled = block_production_override.strip().lower() in {"1", "true", "yes", "on"}

    if block_production_enabled and settings.proposer_id:
        # Outside the try below: that block turns any failure into a warning and carries on,
        # which is how a node with no usable key still went on to append unsigned blocks.
        from .proposer_identity import assert_can_sign

        assert_can_sign(settings.proposer_id, settings.proposer_key, settings.keystore_path)

        try:
            from .consensus import PoAProposer, ProposerConfig

            supported_chains = [c.strip() for c in settings.supported_chains.split(",") if c.strip()]
            if not supported_chains and settings.chain_id:
                supported_chains = [settings.chain_id]
            for chain_id in supported_chains:
                proposer_config = ProposerConfig(
                    chain_id=chain_id,
                    proposer_id=settings.proposer_id,
                    interval_seconds=settings.block_time_seconds,
                    max_block_size_bytes=settings.max_block_size_bytes,
                    max_txs_per_block=settings.max_txs_per_block,
                    default_peer_rpc_url=settings.default_peer_rpc_url,
                )
                proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
                set_poa_proposer(proposer)
                create_task_with_logging(proposer.start(), name="poa_proposer_start")
                proposers.append(proposer)
        except Exception as e:
            _app_logger.warning("Failed to initialize PoA proposer for mining: %s", e)

    try:
        from .services.balance_tracker import init_balance_tracker

        init_balance_tracker(session_scope)
    except Exception as e:
        _app_logger.warning("Failed to initialize balance tracker: %s", e)

    # Initialize cross-chain bridge (enables /rpc/bridge/* endpoints)
    try:
        from .cross_chain.bridge import get_cross_chain_bridge, init_cross_chain_bridge

        init_cross_chain_bridge(session_scope)
        bridge = get_cross_chain_bridge()
        if bridge:
            bridge.ensure_supported_chain_validators()
            _app_logger.info("Bridge validator backfill completed")
            create_task_with_logging(bridge.start_finalizer(), name="bridge_release_finalizer")
            _app_logger.info("Bridge release finalizer started")
        _app_logger.info("Cross-chain bridge initialized")
    except Exception as e:
        _app_logger.warning("Failed to initialize cross-chain bridge: %s", e)

    # Consolidated startup summary
    _app_logger.info(
        "Blockchain node started: chains=%s mode=%s role=%s hardware=%s block_prod=%s",
        settings.supported_chains,
        settings.blockchain_mode,
        settings.market_role,
        settings.hardware_profile,
        block_production_enabled,
    )

    try:
        await lease_tracker.start()
        node_type = "hub" if settings.blockchain_mode == "hub" else "follower"
        _app_logger.info("Lease tracker started on %s node (RPC service)", node_type)
    except Exception as e:
        _app_logger.error("Failed to start lease tracker in RPC service: %s", e)

    try:
        yield
    finally:
        # Bounded shutdown so systemd does not need the full 90s stop timeout.
        # The backends are responsible for fast cleanup; the waits here are a
        # safety net for any component that still blocks.
        async def _shutdown() -> None:
            for proposer in proposers:
                try:
                    await asyncio.wait_for(proposer.stop(), timeout=10.0)
                except asyncio.TimeoutError:
                    _app_logger.warning("PoA proposer stop timed out during shutdown")
                except Exception as exc:
                    _app_logger.warning("Failed to stop PoA proposer during shutdown: %s", exc)
            try:
                await asyncio.wait_for(gossip_broker.shutdown(), timeout=10.0)
            except asyncio.TimeoutError:
                _app_logger.warning("Gossip broker shutdown timed out during shutdown")
            except Exception as exc:
                _app_logger.warning("Failed to shut down gossip broker: %s", exc)
            try:
                await asyncio.wait_for(lease_tracker.stop(), timeout=5.0)
            except asyncio.TimeoutError:
                _app_logger.warning("Lease tracker stop timed out during shutdown")
            except Exception as exc:
                _app_logger.warning("Failed to stop lease tracker: %s", exc)
            _app_logger.info("Blockchain node stopped")

        await _shutdown()


def create_app() -> FastAPI:
    configure_logging(level="INFO")
    app = FastAPI(title="AITBC Blockchain Node", version="v0.2.2", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # app.add_middleware(RateLimitMiddleware, max_requests=100000, window_seconds=60)
    setup_cors(
        app,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )
    app.include_router(rpc_router, prefix="/rpc", tags=["rpc"])
    # Also mount the RPC router under /v1 so the public API examples
    # (e.g. /v1/blocks/{height}) work against the blockchain node directly.
    app.include_router(rpc_router, prefix="/v1", tags=["v1"])
    app.include_router(websocket_router, prefix="/rpc")
    app.include_router(escrow_router, prefix="/rpc")
    if marketplace_router:
        app.include_router(marketplace_router, prefix="/rpc", tags=["marketplace"])
    metrics_router = APIRouter()

    @metrics_router.get("/metrics", response_class=PlainTextResponse, tags=["metrics"], summary="Prometheus metrics")
    async def metrics() -> PlainTextResponse:
        default_metrics = generate_latest()
        legacy_metrics = metrics_registry.render_prometheus().encode()
        if legacy_metrics.strip():
            content = default_metrics + b"\n" + legacy_metrics
        else:
            content = default_metrics
        return PlainTextResponse(content=content, media_type=CONTENT_TYPE_LATEST)

    @metrics_router.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "supported_chains": [c.strip() for c in settings.supported_chains.split(",") if c.strip()],
            "proposer_id": settings.proposer_id,
        }

    app.include_router(metrics_router)
    return app


app = create_app()
