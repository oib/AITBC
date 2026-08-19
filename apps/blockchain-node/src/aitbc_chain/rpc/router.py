from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from aitbc.rate_limiting import rate_limit

from ..logger import get_logger
from ..mempool import get_mempool as get_mempool_instance
from .auth import get_authenticated_address, security
from .transactions import TransactionRequest  # noqa: F401  # re-exported for backward compatibility

_logger = get_logger(__name__)


def _import_failed(module_name: str, error: Exception) -> None:
    """Log a failed optional import at ERROR level and optionally fail fast.

    Bug 10: Previously these failures were logged at WARNING level and silently
    degraded the affected endpoints to 503. They are now logged at ERROR so
    operators notice. Set ``STRICT_IMPORTS=true`` to make the node refuse to
    start when a core module is missing (recommended for production).
    """
    msg = "%s not available: %s — affected endpoints will return 503"
    if os.getenv("STRICT_IMPORTS", "false").lower() == "true":
        _logger.error(msg, module_name, error)
        raise RuntimeError(f"STRICT_IMPORTS is enabled: {module_name} import failed: {error}") from error
    _logger.error(msg, module_name, error)


router = APIRouter()

# Include sub-routers
try:
    from .routers.disputes import router as disputes_router

    router.include_router(disputes_router)
except ImportError as e:
    _import_failed("Disputes sub-router", e)

try:
    from .routers.contracts import router as contracts_router

    router.include_router(contracts_router)
except ImportError as e:
    _import_failed("Contracts sub-router", e)

try:
    from .routers.islands import router as islands_router

    router.include_router(islands_router)
except ImportError as e:
    _import_failed("Islands sub-router", e)

try:
    from .routers.subscription import router as subscription_router

    router.include_router(subscription_router)
except ImportError as e:
    _import_failed("Subscription sub-router", e)

try:
    from .routers.core import router as core_router

    router.include_router(core_router)
except ImportError as e:
    _import_failed("Core sub-router", e)

try:
    from .routers.staking import router as staking_router

    router.include_router(staking_router)
except ImportError as e:
    _import_failed("Staking sub-router", e)

try:
    from .routers.consensus import router as consensus_router

    router.include_router(consensus_router)
except ImportError as e:
    _import_failed("Consensus sub-router", e)

try:
    from .routers.settlement import router as settlement_router

    router.include_router(settlement_router)
except ImportError as e:
    _import_failed("Settlement sub-router", e)

try:
    from .routers.bridge import router as bridge_router

    router.include_router(bridge_router)
except ImportError as e:
    _import_failed("Bridge sub-router", e)

try:
    from .routers.cross_chain import router as cross_chain_router

    router.include_router(cross_chain_router)
except ImportError as e:
    _import_failed("Cross-chain sub-router", e)

try:
    from .gpu_resources import *  # noqa: F403
except ImportError as e:
    _import_failed("GPU resources module", e)
try:
    from .ai_services import *  # noqa: F403
except ImportError as e:
    _import_failed("AI services module", e)
_last_import_time = 0
_import_lock = asyncio.Lock()


@router.post("/mining/start", summary="Start mining")
@rate_limit(rate=10, per=60)
async def start_mining_route(
    request: Request,
    mining_data: dict,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """Start mining with specified wallet (requires admin authentication)"""
    # Bug 9: Add admin authentication to mining endpoints
    admin_address = get_authenticated_address(request, credentials)
    miner_address = mining_data.get("miner_address")
    threads = mining_data.get("threads", 1)
    if not miner_address:
        raise HTTPException(status_code=400, detail="miner_address is required")
    if not hasattr(start_mining_route, "miners"):
        start_mining_route.miners = {}  # type: ignore[attr-defined]
    start_mining_route.miners[miner_address] = {  # type: ignore[attr-defined]
        "address": miner_address,
        "threads": threads,
        "enabled": True,
        "started_at": datetime.now(UTC).isoformat(),
        "authorized_by": admin_address,
    }
    return {"status": "started", "miner_address": miner_address, "threads": threads, "message": "Mining started successfully"}


@router.post("/mining/stop", summary="Stop mining")
@rate_limit(rate=10, per=60)
async def stop_mining_route(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """Stop all mining operations (requires admin authentication)"""
    # Bug 9: Add admin authentication to mining endpoints
    get_authenticated_address(request, credentials)
    if hasattr(start_mining_route, "miners"):
        for miner in start_mining_route.miners.values():
            miner["enabled"] = False
            miner["stopped_at"] = datetime.now(UTC).isoformat()
    return {"status": "stopped", "message": "Mining stopped successfully"}


@router.get("/mining/status", summary="Get mining status")
@rate_limit(rate=100, per=60)
async def get_mining_status_route(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """Get current mining status (requires admin authentication).

    v0.6.7: Aggregates status from coordinator-api miner registry. Falls back
    to local in-memory miners if coordinator-api is unavailable.
    """
    # Bug 9: Add admin authentication to mining endpoints
    get_authenticated_address(request, credentials)

    # v0.6.7: Query coordinator-api for registered miners
    import os

    import httpx

    coordinator_url = os.getenv("COORDINATOR_API_URL", "http://localhost:8203")
    coordinator_miners: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{coordinator_url}/v1/miners")
            if resp.status_code == 200:
                data = resp.json()
                coordinator_miners = data.get("miners", []) if isinstance(data, dict) else data
    except Exception:
        pass  # Fall back to local miners

    if coordinator_miners:
        active = [m for m in coordinator_miners if m.get("status") == "active"]
        return {
            "status": "mining" if active else "idle",
            "miners": coordinator_miners,
            "active_count": len(active),
            "source": "coordinator-api",
        }

    # Fallback: local in-memory miners
    if not hasattr(start_mining_route, "miners"):
        return {"status": "idle", "miners": [], "active_count": 0, "source": "local"}
    active_miners = [m for m in start_mining_route.miners.values() if m.get("enabled", False)]
    return {
        "status": "mining" if active_miners else "idle",
        "miners": list(start_mining_route.miners.values()),
        "active_count": len(active_miners),
        "source": "local",
    }


@router.get("/mining/miners", summary="List active miners")
@rate_limit(rate=100, per=60)
async def list_miners_route(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """List all registered miners (requires admin authentication).

    v0.6.7: Queries coordinator-api miner registry. Falls back to local
    in-memory miners if coordinator-api is unavailable.
    """
    # Bug 9: Add admin authentication to mining endpoints (this endpoint was previously unauthenticated)
    get_authenticated_address(request, credentials)

    # v0.6.7: Query coordinator-api for registered miners
    import os

    import httpx

    coordinator_url = os.getenv("COORDINATOR_API_URL", "http://localhost:8203")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{coordinator_url}/v1/miners")
            if resp.status_code == 200:
                data = resp.json()
                miners = data.get("miners", []) if isinstance(data, dict) else data
                return {"miners": miners, "count": len(miners), "source": "coordinator-api"}
    except Exception:
        pass  # Fall back to local miners

    # Fallback: local in-memory miners
    if not hasattr(start_mining_route, "miners"):
        return {"miners": [], "count": 0, "source": "local"}
    return {"miners": list(start_mining_route.miners.values()), "count": len(start_mining_route.miners), "source": "local"}


@router.get("/pending", summary="Get pending transactions")
@rate_limit(rate=100, per=60)
async def get_pending_transactions_route(request: Request, chain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get pending transactions from mempool (alias for /mempool)"""
    try:
        mempool = get_mempool_instance()
        pending_txs = mempool.get_pending_transactions(chain_id=chain_id, limit=limit)
        return {"transactions": pending_txs, "count": len(pending_txs)}
    except Exception as e:
        _logger.error("Error getting pending transactions: %s", e)
        return {"transactions": [], "count": 0, "error": str(e)}
