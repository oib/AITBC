"""Settlement endpoints for the Trading Service.

#2385: the inter-chain HTLC settlement rail is retired — the node-side
``/rpc/bridge/settlement/*`` mutating endpoints answer HTTP 410 because
HTLC emissions carry no ``payload.auth`` and cannot seal at block version
9. ``lock-escrow`` therefore refuses up front instead of creating a
bookkeeping escrow that could never lock, and ``settle`` refuses for the
same reason. Only the read-only ``settlement-status`` endpoint stays live
so existing trades remain inspectable.
"""

import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy import select

from aitbc.aitbc_logging import get_logger
from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.settlement.client import SettlementClient
from aitbc.settlement.types import SettlementConfig
from aitbc.trading.types import InterChainTradeStatus, SettlementPhase
from ..dependencies import get_inter_chain_service
from ..domain.inter_chain import InterChainTrade

from ..services.inter_chain_service import InterChainTradeService

router = APIRouter(tags=["settlement"])
logger = get_logger(__name__)

# Literal 410 detail shared by the retired mutating endpoints (#2385).
_SETTLEMENT_RETIRED_DETAIL = (
    "inter-chain HTLC settlement is retired: protocol-escrow transfers emit no "
    "payload.auth and cannot seal at block version 9; see #2385"
)

# Expected failure surface for the settlement-status read below: HTTP/RPC
# I/O from the settlement client (httpx), config ValueErrors, and
# data-shape errors. RuntimeError covers abort-style raises; genuine
# BaseExceptions still propagate (#1862).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    httpx.HTTPError,
)


def _get_settlement_client() -> SettlementClient:
    """Create a SettlementClient targeting the blockchain node settlement RPC."""
    rpc_url = os.getenv("SETTLEMENT_RPC_URL", BLOCKCHAIN_RPC_URL)
    config = SettlementConfig(settlement_rpc_url=rpc_url)
    return SettlementClient(config)


async def _lock_trade_for_update(svc: InterChainTradeService, trade_id: str) -> InterChainTrade | None:
    """Load a trade with SELECT ... FOR UPDATE (or BEGIN IMMEDIATE on sqlite)."""
    stmt = select(InterChainTrade).where(InterChainTrade.trade_id == trade_id)  # type: ignore[arg-type]
    # with_for_update is a no-op on SQLite but acquires row locks on PostgreSQL/MySQL
    result = await svc.session.execute(stmt.with_for_update())
    return result.scalars().first()


# #1562: node escrow status -> local settlement phase. ``failed`` has no
# SettlementPhase value; it is handled as a trade-status failure below.
_REMOTE_TO_SETTLEMENT_PHASE = {
    "pending": SettlementPhase.ESCROW_CREATED,
    "locked": SettlementPhase.ESCROW_LOCKED,
    "verified": SettlementPhase.LOCK_VERIFIED,
    "executing": SettlementPhase.TRADE_EXECUTED,
    "completed": SettlementPhase.SETTLED,
    "refunded": SettlementPhase.REFUNDED,
    "disputed": SettlementPhase.DISPUTED,
}

# Monotonic rank so a stale/late remote read cannot regress a fresher local
# phase. Claim markers rank with the step they guard: ``escrow_creating`` is
# below ``escrow_created`` (a remote pending may recover a lost create commit),
# while ``settling``/``disputed`` sit above in-flight escrow states but below
# the terminal phases.
_PHASE_RANK = {
    SettlementPhase.NONE.value: 0,
    SettlementPhase.ESCROW_CREATING.value: 1,
    SettlementPhase.ESCROW_CREATED.value: 2,
    SettlementPhase.ESCROW_LOCKED.value: 3,
    SettlementPhase.LOCK_VERIFIED.value: 4,
    SettlementPhase.TRADE_EXECUTED.value: 5,
    SettlementPhase.SETTLING.value: 6,
    SettlementPhase.DISPUTED.value: 6,
    SettlementPhase.SETTLED.value: 7,
    SettlementPhase.REFUNDED.value: 7,
}
_LOCAL_TERMINAL_PHASES = {SettlementPhase.SETTLED.value, SettlementPhase.REFUNDED.value}
_LOCAL_TERMINAL_STATUSES = {
    InterChainTradeStatus.COMPLETED.value,
    InterChainTradeStatus.CANCELLED.value,
    InterChainTradeStatus.FAILED.value,
}


async def _sync_trade_from_escrow_status(
    svc: InterChainTradeService, trade_id: str, escrow_status: str
) -> InterChainTrade | None:
    """Write a node-reported escrow status back onto the trade row (#1562).

    The settlement-status endpoint used to be read-only: a node-side refund
    (timeout monitor, dispute resolution) stayed invisible locally, leaving
    ``settlement_phase='escrow_created'``/``status='matched'`` and letting a
    later ``settle`` attempt fail against an already-refunded escrow.

    The sync is lazy (runs when status is polled), monotonic (never regresses
    a fresher local phase), and terminal-local-state preserving: once the row
    is ``settled``/``refunded`` or the trade status is completed/cancelled/
    failed, remote reads do not rewrite it.
    """
    remote = str(escrow_status).strip().lower()
    if remote in {"", "unknown"}:
        return None
    remote_phase = _REMOTE_TO_SETTLEMENT_PHASE.get(remote)
    remote_failed = remote == "failed"
    if remote_phase is None and not remote_failed:
        return None

    trade = await _lock_trade_for_update(svc, trade_id)
    if trade is None or not trade.escrow_id:
        return None
    if trade.settlement_phase in _LOCAL_TERMINAL_PHASES:
        return trade

    changed = False
    if remote_phase is not None:
        current_rank = _PHASE_RANK.get(trade.settlement_phase, 0)
        remote_rank = _PHASE_RANK[remote_phase.value]
        # A remote terminal phase always wins over a non-terminal local phase;
        # non-terminal remote phases must not move backwards.
        if remote_rank >= current_rank or remote_phase.value in _LOCAL_TERMINAL_PHASES:
            if trade.settlement_phase != remote_phase.value:
                trade.settlement_phase = remote_phase.value
                changed = True
    if remote in {"completed", "refunded", "failed"} and trade.status not in _LOCAL_TERMINAL_STATUSES:
        trade.status = InterChainTradeStatus.COMPLETED.value if remote == "completed" else InterChainTradeStatus.FAILED.value
        changed = True
    if not changed:
        return trade
    trade.updated_at = datetime.now(UTC)
    await svc.session.commit()
    await svc.session.refresh(trade)
    return trade


@router.post("/v1/trading/trades/{trade_id}/lock-escrow")
async def lock_escrow(
    trade_id: str,
    timeout_seconds: Annotated[int | None, Body(embed=True)] = None,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # type: ignore[assignment]  # noqa: B008
):
    """Retired (#2385): inter-chain HTLC settlement cannot seal at block v9.

    Previously this created a cross-chain escrow record via the node
    settlement RPC — a row that could never lock, verify, or settle. It now
    refuses with 410 for any existing trade (404 for an unknown one) and
    never touches the settlement RPC or the trade row.
    """
    trade = await _lock_trade_for_update(svc, trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return JSONResponse(status_code=410, content={"error": _SETTLEMENT_RETIRED_DETAIL})


@router.post("/v1/trading/trades/{trade_id}/settle")
async def settle_trade(
    trade_id: str,
    secret: Annotated[str, Body(embed=True)],
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # type: ignore[assignment]  # noqa: B008
):
    """Retired (#2385): inter-chain HTLC settlement cannot seal at block v9.

    Previously this revealed the HTLC secret via the node settlement RPC.
    It now refuses with 410 for any existing trade (404 for an unknown
    one); ``settlement-status`` remains the read-only check.
    """
    trade = await _lock_trade_for_update(svc, trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return JSONResponse(status_code=410, content={"error": _SETTLEMENT_RETIRED_DETAIL})


@router.get("/v1/trading/trades/{trade_id}/settlement-status")
async def settlement_status(
    trade_id: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # type: ignore[assignment]  # noqa: B008
):
    """Get settlement status for a trade.

    Returns the trade's local settlement_phase and, if an escrow exists,
    queries the blockchain-node settlement RPC for the live escrow status.
    """
    trade = await svc.get_trade(trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    escrow_status: str | None = None
    sync_error: str | None = None
    if trade.escrow_id:
        try:
            async with _get_settlement_client() as client:
                escrow_status = await client.get_escrow_status(trade.escrow_id)
            # #1562: mirror node-side terminal/progress states onto the trade
            # row so refunds and completions are not invisible locally. A sync
            # failure must not break the status read — the remote status is
            # still reported below.
            try:
                synced = await _sync_trade_from_escrow_status(svc, trade_id, escrow_status)
                if synced is not None:
                    trade = synced
            except Exception as exc:
                sync_error = str(exc)
                logger.exception("Settlement status sync failed for trade %s", trade_id)
        except _OPS_ERRORS as e:
            logger.error("Get settlement status failed for trade %s: %s", trade_id, e)
            escrow_status = "unknown"
            sync_error = str(e)
    response: dict[str, Any] = {
        "trade_id": trade.trade_id,
        "settlement_phase": trade.settlement_phase,
        "escrow_id": trade.escrow_id,
    }
    if escrow_status is not None:
        response["escrow_status"] = escrow_status
    if sync_error is not None:
        response["error"] = sync_error
    return response
