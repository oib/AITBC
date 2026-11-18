from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..base_models import MinerRegistry
from ..chain_id import resolve_chain_id
from ..database import session_scope
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
    from .routers.messaging import router as messaging_router

    router.include_router(messaging_router)
except ImportError as e:
    _import_failed("Messaging sub-router", e)

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
    from .routers.liquidity import router as liquidity_router

    router.include_router(liquidity_router)
except ImportError as e:
    _import_failed("Liquidity sub-router", e)

try:
    from .routers.bond import router as bond_router

    router.include_router(bond_router)
except ImportError as e:
    _import_failed("Bond sub-router", e)

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
    from .routers.agent_economy import router as agent_economy_router

    router.include_router(agent_economy_router)
except ImportError as e:
    _import_failed("Agent economy sub-router", e)

try:
    from .routers.bounty import router as bounty_router

    router.include_router(bounty_router)
except ImportError as e:
    _import_failed("Bounty sub-router", e)

try:
    from .routers.bridge import bridge_oracle_status_route, bridge_security_status_route, router as bridge_router

    router.include_router(bridge_router)
except ImportError as e:
    bridge_oracle_status_route = None  # type: ignore[assignment]
    bridge_security_status_route = None  # type: ignore[assignment]
    _import_failed("Bridge sub-router", e)

try:
    from .routers.bridge_ledger import router as bridge_ledger_router

    router.include_router(bridge_ledger_router)
except ImportError as e:
    _import_failed("Bridge ledger sub-router", e)


@router.get("/security-status", summary="Bridge security status (runbook alias)")
@rate_limit(rate=100, per=60)
def rpc_security_status_route(request: Request) -> dict[str, Any]:
    """Runbook probe alias for GET /bridge/security/status.

    Ops runbooks probe ``/rpc/security-status``; the canonical handler lives
    under the bridge sub-router. This thin alias keeps the runbook paths valid.
    """
    if bridge_security_status_route is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return bridge_security_status_route(request)  # type: ignore[no-any-return]


@router.get("/oracle-status", summary="Bridge oracle/verification status (runbook alias)")
@rate_limit(rate=100, per=60)
def rpc_oracle_status_route(request: Request) -> dict[str, Any]:
    """Runbook probe alias for GET /bridge/oracle/status."""
    if bridge_oracle_status_route is None:
        raise HTTPException(status_code=503, detail="Bridge module not available")
    return bridge_oracle_status_route(request)  # type: ignore[no-any-return]


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


# #2211: the chain is PBFT/PoA — there is no proof-of-work mining, so these
# endpoints are admin bookkeeping stubs (no hashrate, blocks, or rewards).
# Miner state lives in the chain.db ``miner_registry`` table so every RPC
# worker agrees; it previously lived in a per-process function attribute and
# the read paths preferred the unrelated coordinator-api ``/v1/miners``
# AI-job registry, so start/stop/status/list could never agree.
_MINING_SIMULATED_NOTE = (
    "simulated bookkeeping only: this is a PBFT/PoA chain with no proof-of-work "
    "mining — no hashrate, blocks mined, or rewards are produced"
)


def _miner_public(row: MinerRegistry) -> dict[str, Any]:
    return {
        "address": row.miner_address,
        "threads": row.threads,
        "enabled": row.enabled,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "stopped_at": row.stopped_at.isoformat() if row.stopped_at else None,
        "authorized_by": row.authorized_by,
    }


def _registry_rows(chain_id: str) -> list[dict[str, Any]]:
    """All miner_registry rows for the chain, serialized inside the session."""
    with session_scope(chain_id) as session:
        rows = session.exec(select(MinerRegistry).where(MinerRegistry.chain_id == chain_id)).all()
        return [_miner_public(row) for row in rows]


@router.post("/mining/start", summary="Start mining")
@rate_limit(rate=10, per=60)
def start_mining_route(
    request: Request,
    mining_data: dict,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """Record a miner as started (requires admin authentication).

    Bookkeeping stub only — PBFT/PoA has no proof-of-work mining (#2211).
    """
    # Bug 9: Add admin authentication to mining endpoints
    admin_address = get_authenticated_address(request, credentials)
    miner_address = mining_data.get("miner_address")
    threads = mining_data.get("threads", 1)
    if not miner_address or not isinstance(miner_address, str):
        raise HTTPException(status_code=400, detail="miner_address is required")
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1:
        raise HTTPException(status_code=400, detail="threads must be a positive integer")

    chain_id = resolve_chain_id()
    with session_scope(chain_id) as session:
        row = session.exec(
            select(MinerRegistry).where(
                MinerRegistry.chain_id == chain_id,
                MinerRegistry.miner_address == miner_address,
            )
        ).first()
        now = datetime.now(UTC)
        if row is None:
            session.add(
                MinerRegistry(
                    chain_id=chain_id,
                    miner_address=miner_address,
                    threads=threads,
                    enabled=True,
                    authorized_by=admin_address,
                    started_at=now,
                )
            )
        else:
            row.threads = threads
            row.enabled = True
            row.authorized_by = admin_address
            row.started_at = now
            row.stopped_at = None
        session.commit()
    return {
        "status": "started",
        "miner_address": miner_address,
        "threads": threads,
        "simulated": True,
        "note": _MINING_SIMULATED_NOTE,
        "message": "Mining started successfully",
    }


@router.post("/mining/stop", summary="Stop mining")
@rate_limit(rate=10, per=60)
def stop_mining_route(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """Disable all recorded miners (requires admin authentication).

    Bookkeeping stub only — PBFT/PoA has no proof-of-work mining (#2211).
    """
    # Bug 9: Add admin authentication to mining endpoints
    get_authenticated_address(request, credentials)

    chain_id = resolve_chain_id()
    with session_scope(chain_id) as session:
        rows = session.exec(select(MinerRegistry).where(MinerRegistry.chain_id == chain_id)).all()
        now = datetime.now(UTC)
        for row in rows:
            row.enabled = False
            row.stopped_at = now
        session.commit()
    return {
        "status": "stopped",
        "simulated": True,
        "note": _MINING_SIMULATED_NOTE,
        "message": "Mining stopped successfully",
    }


@router.get("/mining/status", summary="Get mining status")
@rate_limit(rate=100, per=60)
def get_mining_status_route(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """Get current mining bookkeeping status (requires admin authentication).

    Reads the shared chain.db ``miner_registry`` table so every RPC worker
    agrees (#2211). Bookkeeping stub only — PBFT/PoA has no PoW mining.
    """
    # Bug 9: Add admin authentication to mining endpoints
    get_authenticated_address(request, credentials)

    miners = _registry_rows(resolve_chain_id())
    active_miners = [m for m in miners if m["enabled"]]
    return {
        "status": "mining" if active_miners else "idle",
        "miners": miners,
        "active_count": len(active_miners),
        "source": "chain.db",
        "simulated": True,
        "note": _MINING_SIMULATED_NOTE,
    }


@router.get("/mining/miners", summary="List active miners")
@rate_limit(rate=100, per=60)
def list_miners_route(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> dict[str, Any]:
    """List recorded miners (requires admin authentication).

    Reads the shared chain.db ``miner_registry`` table so every RPC worker
    agrees (#2211). Bookkeeping stub only — PBFT/PoA has no PoW mining.
    """
    # Bug 9: Add admin authentication to mining endpoints (this endpoint was previously unauthenticated)
    get_authenticated_address(request, credentials)

    miners = _registry_rows(resolve_chain_id())
    return {
        "miners": miners,
        "count": len(miners),
        "source": "chain.db",
        "simulated": True,
        "note": _MINING_SIMULATED_NOTE,
    }


@router.get("/pending", summary="Get pending transactions")
@rate_limit(rate=100, per=60)
def get_pending_transactions_route(request: Request, chain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get pending transactions from mempool (alias for /mempool)"""
    try:
        mempool = get_mempool_instance()
        pending_txs = mempool.get_pending_transactions(chain_id=chain_id, limit=limit)
        return {"transactions": pending_txs, "count": len(pending_txs)}
    except (SQLAlchemyError, OSError, ValueError, TypeError, RuntimeError, AttributeError, LookupError) as e:
        _logger.error("Error getting pending transactions: %s", e)
        return {"transactions": [], "count": 0, "error": str(e)}
