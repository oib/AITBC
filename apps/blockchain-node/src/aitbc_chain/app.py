from __future__ import annotations
import asyncio
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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
marketplace_router: Optional[APIRouter]
try:
    from .rpc.marketplace import router as marketplace_router
except ImportError:
    marketplace_router = None
_app_logger = get_logger('aitbc_chain.app')

def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return None

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit requests by client IP."""

    def __init__(self, app: Any, max_requests: int=1000, window_seconds: int=60) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        client_ip = request.client.host if request.client else 'unknown'
        now = time.time()
        self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < self._window]
        if len(self._requests[client_ip]) >= self._max_requests:
            metrics_registry.increment('rpc_rate_limited_total')
            return JSONResponse(status_code=429, content={'detail': 'Rate limit exceeded'}, headers={'Retry-After': str(self._window)})
        self._requests[client_ip].append(now)
        return await call_next(request)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and error details."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start
            metrics_registry.observe('rpc_request_duration_seconds', duration)
            metrics_registry.increment('rpc_requests_total')
            if response.status_code >= 500:
                metrics_registry.increment('rpc_server_errors_total')
                _app_logger.error('Server error', extra={'method': method, 'path': path, 'status': response.status_code, 'duration_ms': round(duration * 1000, 2)})
            elif response.status_code >= 400:
                metrics_registry.increment('rpc_client_errors_total')
            return response
        except HTTPException:
            raise
        except Exception as exc:
            duration = time.perf_counter() - start
            metrics_registry.increment('rpc_unhandled_errors_total')
            _app_logger.exception('Unhandled error in request', extra={'method': method, 'path': path, 'error': str(exc), 'duration_ms': round(duration * 1000, 2)})
            return JSONResponse(status_code=503, content={'detail': 'Internal server error'})

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    from .contracts.escrow import create_escrow_manager
    create_escrow_manager()
    _app_logger.info('EscrowManager initialised')
    init_mempool(backend=settings.mempool_backend, db_url=settings.mempool_db_url, max_size=settings.mempool_max_size, min_fee=settings.min_fee)
    _app_logger.info('Initializing gossip backend: %s, url: %s', settings.gossip_backend, settings.gossip_broadcast_url)
    create_backend('broadcast', broadcast_url=settings.gossip_broadcast_url)
    _app_logger.info('Gossip backend initialized successfully')
    try:
        node_id = os.getenv('NODE_ID', 'unknown-node')
        default_island_id = os.getenv('DEFAULT_ISLAND_ID', f"{settings.supported_chains.split(',')[0].strip()}-island")
        default_chain_id = settings.supported_chains.split(',')[0].strip() if settings.supported_chains else 'ait-mainnet'
        island_manager = create_island_manager(node_id, default_island_id, default_chain_id)
        _app_logger.info('Island manager initialized', extra={'node_id': node_id, 'default_island': default_island_id})
    except Exception as e:
        _app_logger.error('Failed to initialize island manager: %s', e, exc_info=True)
    proposers = []
    block_production_override = _env_value('AITBC_FORCE_ENABLE_BLOCK_PRODUCTION', 'ENABLE_BLOCK_PRODUCTION', 'enable_block_production')
    block_production_enabled = settings.enable_block_production
    if block_production_override is not None:
        block_production_enabled = block_production_override.strip().lower() in {'1', 'true', 'yes', 'on'}
    _app_logger.info('Block production enabled: %s, proposer_id: %s', block_production_enabled, settings.proposer_id)
    if block_production_enabled and settings.proposer_id:
        try:
            from .consensus import PoAProposer, ProposerConfig
            supported_chains = [c.strip() for c in settings.supported_chains.split(',') if c.strip()]
            if not supported_chains and settings.chain_id:
                supported_chains = [settings.chain_id]
            for chain_id in supported_chains:
                proposer_config = ProposerConfig(chain_id=chain_id, proposer_id=settings.proposer_id, interval_seconds=settings.block_time_seconds, max_block_size_bytes=settings.max_block_size_bytes, max_txs_per_block=settings.max_txs_per_block, default_peer_rpc_url=settings.default_peer_rpc_url)
                proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
                set_poa_proposer(proposer)
                asyncio.create_task(proposer.start())
                proposers.append(proposer)
            _app_logger.info('PoA proposer initialized for mining integration', extra={'proposer_id': settings.proposer_id, 'supported_chains': supported_chains})
        except Exception as e:
            _app_logger.warning('Failed to initialize PoA proposer for mining: %s', e)
    try:
        from .services.balance_tracker import init_balance_tracker
        init_balance_tracker(session_scope)
        _app_logger.info('Balance tracker initialized')
    except Exception as e:
        _app_logger.warning('Failed to initialize balance tracker: %s', e)
    _app_logger.info('Blockchain node started', extra={'supported_chains': settings.supported_chains, 'blockchain_mode': settings.blockchain_mode, 'market_role': settings.market_role, 'hardware_profile': settings.hardware_profile})
    try:
        await lease_tracker.start()
        if settings.blockchain_mode == 'hub':
            _app_logger.info('Lease tracker started on hub node (RPC service)')
        else:
            _app_logger.info('Lease tracker started on follower node (RPC service)')
    except Exception as e:
        _app_logger.error('Failed to start lease tracker in RPC service: %s', e, exc_info=True)
    try:
        yield
    finally:
        for proposer in proposers:
            try:
                await proposer.stop()
            except Exception as exc:
                _app_logger.warning('Failed to stop PoA proposer during shutdown: %s', exc)
        await gossip_broker.shutdown()
        await lease_tracker.stop()
        _app_logger.info('Blockchain node stopped')

def create_app() -> FastAPI:
    app = FastAPI(title='AITBC Blockchain Node', version='v0.2.2', lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=5000, window_seconds=60)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization', 'X-API-Key'])
    app.include_router(rpc_router, prefix='/rpc', tags=['rpc'])
    app.include_router(websocket_router, prefix='/rpc')
    app.include_router(escrow_router, prefix='/rpc')
    if marketplace_router:
        app.include_router(marketplace_router, prefix='/rpc', tags=['marketplace'])
    metrics_router = APIRouter()

    @metrics_router.get('/metrics', response_class=PlainTextResponse, tags=['metrics'], summary='Prometheus metrics')
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @metrics_router.get('/health', tags=['health'], summary='Health check')
    async def health() -> dict:
        return {'status': 'ok', 'supported_chains': [c.strip() for c in settings.supported_chains.split(',') if c.strip()], 'proposer_id': settings.proposer_id}
    app.include_router(metrics_router)
    return app
app = create_app()