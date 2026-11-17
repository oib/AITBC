"""
Market Service main application
Manages hardware+software bundle market operations
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aitbc.constants import BLOCKCHAIN_RPC_URL as _DEFAULT_RPC_URL
from aitbc.constants import DATA_DIR
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", _DEFAULT_RPC_URL)
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.middleware import setup_cors  # noqa: E402
from aitbc.middleware import (  # noqa: E402
    ErrorHandlerMiddleware,
    LegacyPathRewriteMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
    register_request_validation_error_handler,
)
from aitbc.operations import OperationLedger  # noqa: E402
from aitbc.rate_limiting import RateLimitMiddleware, client_ip_for_rate_limit  # noqa: E402
from aitbc.env_compat import market_getenv  # noqa: E402

from .config import settings  # noqa: E402
from . import operations as _operations_module  # noqa: E402

# Re-exports: the test-suite reaches the auth toggles and the idempotency
# helpers through ``market_service.main.<name>`` — keep them resolving.
from .deps import (  # noqa: E402
    _is_market_admin as _is_market_admin,
    _is_operator as _is_operator,
    _market_operator_key_auth as _market_operator_key_auth,
    _market_user_key_auth as _market_user_key_auth,
    get_market_service as get_market_service,
    get_matching_service as get_matching_service,
    get_session_dep as get_session_dep,
    require_market_api_key as require_market_api_key,
    require_market_operator_key as require_market_operator_key,
)
from .operations import (  # noqa: E402
    _begin_operation as _begin_operation,
    _fail_operation as _fail_operation,
    _reject_operation as _reject_operation,
)
from .storage import init_db  # noqa: E402

configure_logging(level="INFO", service_name="market", to_file=True)
logger = get_logger(__name__)

# SECRET-RELOAD-1 (#1776): reload JWT/API-key secrets from env files on SIGHUP.
try:
    from aitbc.auth import install_auth_reload_signal as _install_auth_reload_signal
except ImportError:  # aitbc.auth unavailable in minimal test envs
    _install_auth_reload_signal = None  # type: ignore[assignment]
if _install_auth_reload_signal is not None:
    _install_auth_reload_signal()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Market Service."""
    from .services.ipfs_rental_sweeper import IpfsRentalSweeper
    from .services.market_job_sweeper import MarketJobSweeper
    from .services.operation_reconciler import OperationReconciler

    logger.info("Starting Market Service")
    await init_db()
    sweeper = IpfsRentalSweeper()
    job_sweeper = MarketJobSweeper()
    ops_reconciler = OperationReconciler(_get_operations_ledger)
    await sweeper.start()
    await job_sweeper.start()
    await ops_reconciler.start()
    try:
        yield
    finally:
        logger.info("Shutting down Market Service")
        await sweeper.stop()
        await job_sweeper.stop()
        await ops_reconciler.stop()


app = FastAPI(
    title="AITBC Market Service",
    description="Manages hardware+software bundle market operations",
    version="0.1.0",
    lifespan=lifespan,
)
# #1676: literal NaN/Infinity JSON must answer a serializable 422, not 500.
register_request_validation_error_handler(app)
setup_cors(app, allow_origins=["http://localhost:3000", "http://localhost:8080"])
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
# V23-32a: this service had no rate limiting at all, while feature_flags.json reported
# `enable_market_rate_limiting` as on at 100% rollout since 2026-05-24.
#
# Middleware rather than the @rate_limit decorator: none of the 38 handlers here declare a
# `request: Request` parameter, so the decorator would find nothing to key on and put every
# caller in one shared bucket -- one client could then lock out the rest. The middleware
# always has the request and keys by client IP.
# #1678: scoped to mutating methods (same as trading/pool-hub) — GET polling
# from dashboards/explorers must not burn the per-IP write budget.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
app.add_middleware(
    RateLimitMiddleware,
    rate=settings.rate_limit_requests,
    per=settings.rate_limit_window_seconds,
    # #1946: trusted-proxy-aware client IP — raw peer is always loopback
    # behind nginx, which collapsed every caller into one shared bucket.
    key_func=client_ip_for_rate_limit,
    methods=_MUTATING_METHODS,
    exclude_paths=["/health", "/ready", "/live", "/metrics"],
    error_message="Market rate limit exceeded",
)
app.add_middleware(ErrorHandlerMiddleware)
# Added last so it wraps everything: the rate limiter and the error handler
# see the canonical path, never the pre-rename /v1/marketplace spelling.
app.add_middleware(LegacyPathRewriteMiddleware)


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str


_operations_ledger: OperationLedger | None = None


def _get_operations_ledger() -> OperationLedger:
    """The market service's operation ledger — one durable row per Idempotency-Key.

    Kept in its own SQLite file beside the service database; the ledger's
    begin/complete calls are single-row writes run via ``asyncio.to_thread``.
    """
    global _operations_ledger
    if _operations_ledger is None:
        db_path = market_getenv("MARKET_OPERATIONS_DB") or str(DATA_DIR / "data" / "market_operations.db")
        _operations_ledger = OperationLedger(db_path, service="market")
    return _operations_ledger


# The idempotency helpers in ``operations`` resolve the ledger through this
# binding so the singleton (and the test-suite's reset of it) stays here.
_operations_module.bind_ledger_getter(_get_operations_ledger)


@app.get("/health")
def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(**create_simple_health_response("market-service"))


@app.get("/ready")
async def ready() -> Any:
    """Readiness check - verifies required dependencies are reachable.

    The service database carries the offers, and the operation ledger (a
    separate sqlite file) carries the replay-safe writes from Phase E; a
    missing ledger means idempotent mutations silently lose their dedup, so
    it is part of readiness, not an afterthought.
    """
    try:
        from .storage import get_session_context

        async with get_session_context() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
        from aitbc.health_checks import run_readiness_checks

        failed = await asyncio.to_thread(run_readiness_checks, {"operations_db": _check_operations_db})
        if failed:
            raise RuntimeError("operations ledger unavailable")
        return {"status": "ready", "service": "market-service"}
    except Exception:
        # A failed dependency check carries the DSN -- host, port, user -- and
        # /ready is unauthenticated, so the reason goes to the log, not the caller.
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "market-service", "error": "readiness check failed"},
        )


def _check_operations_db() -> None:
    """The operation-ledger sqlite file opens and answers a trivial query."""
    import sqlite3

    conn = sqlite3.connect(_get_operations_ledger().db_path)
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()


@app.get("/live")
def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "market-service"}


@app.get("/v1/market/status")
def market_status() -> dict[str, str]:
    """Get market status"""
    return {"status": "operational", "service": "market-service", "message": "Market service is running"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint"""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Route groups — included after all app-level wiring so middleware and
# exception handlers see every route identically to the monolith. Within
# each router the declaration order matches the original file, which matters
# for overlapping templates (e.g. /v1/market/jobs/usage before
# /v1/market/jobs/{job_id}).
from .routers import catalog, jobs, offers  # noqa: E402

app.include_router(offers.router)
app.include_router(jobs.router)
app.include_router(catalog.router)


if __name__ == "__main__":
    import uvicorn

    # Allow configuration via environment variable for multi-node deployments
    # Default to 0.0.0.0 to accept connections from other nodes
    # code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
    host = market_getenv("MARKET_BIND_HOST", "0.0.0.0")
    port = int(market_getenv("MARKET_BIND_PORT", "8102"))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
