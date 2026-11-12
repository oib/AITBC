"""Settlement endpoints for the Trading Service."""

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy import select

from aitbc.aitbc_logging import get_logger
from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.settlement.client import (
    MAX_ESCROW_TIMEOUT_SECONDS,
    MIN_ESCROW_TIMEOUT_SECONDS,
    SettlementClient,
)
from aitbc.settlement.types import SettlementConfig
from aitbc.trading.types import InterChainTradeStatus, SettlementPhase
from ..dependencies import get_inter_chain_service
from ..domain.inter_chain import InterChainTrade

from ..services.inter_chain_service import InterChainTradeService

router = APIRouter(tags=["settlement"])
logger = get_logger(__name__)

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

# Claim-then-call bound for the in-flight markers (#1562): the external
# create_escrow/settle RPCs are bounded by the HTTP timeout, so a marker
# older than this can only mean the claiming request died mid-flight — a
# retry may reclaim it. Fresh markers refuse with 409 so two callers cannot
# both reach the RPC (with_for_update is a no-op on sqlite, the default
# backend).
_ESCROW_CREATE_CLAIM_TTL = timedelta(seconds=300)
_SETTLE_CLAIM_TTL = timedelta(seconds=300)


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


async def _claim_phase(
    svc: InterChainTradeService,
    trade: InterChainTrade,
    trade_id: str,
    marker: SettlementPhase,
    ttl: timedelta,
    in_flight_error: str,
) -> tuple[str, JSONResponse | None]:
    """Commit an in-flight claim marker before the external RPC (#1562).

    ``marker`` is a non-terminal SettlementPhase (``escrow_creating`` /
    ``settling``). Returns ``(prior_phase, refusal)`` — ``refusal`` is a 409
    JSONResponse when a fresh claim by another caller is still within ``ttl``;
    otherwise the marker is committed and ``refusal`` is None.
    """
    prior_phase = trade.settlement_phase
    if prior_phase == marker.value:
        claimed_at = trade.updated_at
        if claimed_at is not None and claimed_at.tzinfo is None:
            claimed_at = claimed_at.replace(tzinfo=UTC)
        if claimed_at is not None and datetime.now(UTC) - claimed_at < ttl:
            return prior_phase, JSONResponse(status_code=409, content={"error": in_flight_error})
        logger.warning("Reclaiming stale %s claim on trade %s", marker.value, trade_id)
    trade.settlement_phase = marker.value
    trade.updated_at = datetime.now(UTC)
    await svc.session.commit()
    await svc.session.refresh(trade)
    return prior_phase, None


async def _release_phase_claim(svc: InterChainTradeService, trade_id: str, marker: SettlementPhase, prior_phase: str) -> None:
    """Undo the claim marker after a failed external RPC so the trade can retry."""
    try:
        trade = await _lock_trade_for_update(svc, trade_id)
        if trade is not None and trade.settlement_phase == marker.value:
            trade.settlement_phase = prior_phase
            trade.updated_at = datetime.now(UTC)
            await svc.session.commit()
    except Exception:
        await svc.session.rollback()
        logger.exception("Failed to release %s claim on trade %s", marker.value, trade_id)


async def _claim_escrow_creation(
    svc: InterChainTradeService, trade: InterChainTrade, trade_id: str
) -> tuple[str, JSONResponse | None]:
    """Commit the ``escrow_creating`` claim marker before create_escrow (#1562)."""
    return await _claim_phase(
        svc,
        trade,
        trade_id,
        SettlementPhase.ESCROW_CREATING,
        _ESCROW_CREATE_CLAIM_TTL,
        "Escrow creation already in progress for this trade",
    )


async def _release_escrow_claim(svc: InterChainTradeService, trade_id: str, prior_phase: str) -> None:
    """Undo the escrow_creating claim after a failed create_escrow."""
    await _release_phase_claim(svc, trade_id, SettlementPhase.ESCROW_CREATING, prior_phase)


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
    """Initiate escrow lock for a trade.

    Looks up the inter-chain trade, extracts source/dest chain, sender,
    recipient, and amount, then calls the blockchain-node settlement RPC
    to create a cross-chain escrow. Persists the returned escrow_id,
    secret_hash, and timelocks on the trade record.

    Idempotent: if the trade already has an escrow_id, returns the existing
    escrow info instead of creating a duplicate.
    """
    trade = await _lock_trade_for_update(svc, trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    # Idempotency: reject duplicate escrow creation
    if trade.escrow_id:
        return JSONResponse(
            status_code=409,
            content={
                "error": "Escrow already created for this trade",
                "trade_id": trade.trade_id,
                "escrow_id": trade.escrow_id,
                "settlement_phase": trade.settlement_phase,
            },
        )
    # #1415: only live trades may lock funds — a cancelled/completed/failed
    # trade must never get a real HTLC escrow created for it.
    if trade.status not in {"pending", "matched", "locked", "confirmed"}:
        return JSONResponse(
            status_code=409,
            content={"error": f"Trade status '{trade.status}' cannot lock an escrow"},
        )
    if trade.amount <= 0:
        return JSONResponse(status_code=400, content={"error": "Trade amount must be positive"})
    # #1575: timeout_seconds is caller-supplied and forwarded to the settlement
    # RPC unchecked — bound it before it becomes block-height timelocks. Runs
    # before the claim below so a rejected request leaves no marker behind.
    if timeout_seconds is not None and not (MIN_ESCROW_TIMEOUT_SECONDS <= timeout_seconds <= MAX_ESCROW_TIMEOUT_SECONDS):
        # Literal message on purpose: the openapi enricher AST-scans this
        # return and would publish f-string placeholders verbatim. The
        # numbers mirror MIN/MAX_ESCROW_TIMEOUT_SECONDS (60s / 7d).
        return JSONResponse(
            status_code=400,
            content={"error": "timeout_seconds must be between 60 and 604800 seconds"},
        )

    # Claim-then-call (#1562): the committed marker is the guard on every
    # backend, including sqlite where FOR UPDATE is a no-op — see
    # _claim_escrow_creation.
    prior_phase, refusal = await _claim_escrow_creation(svc, trade, trade_id)
    if refusal is not None:
        return refusal

    try:
        async with _get_settlement_client() as client:
            escrow = await client.create_escrow(
                trade_id=trade.trade_id,
                source_chain=trade.source_chain,
                dest_chain=trade.dest_chain,
                sender=trade.sender,
                recipient=trade.recipient,
                amount=trade.amount,
                timeout_seconds=timeout_seconds,
            )
        # Persist settlement fields on the trade record
        trade.escrow_id = escrow.get("escrow_id")
        # #1414: the column stores SettlementPhase values — "pending" is not one.
        trade.settlement_phase = SettlementPhase.ESCROW_CREATED.value
        trade.secret_hash = escrow.get("secret_hash", "")
        trade.source_timelock = escrow.get("source_timelock", 0)
        trade.dest_timelock = escrow.get("dest_timelock", 0)
        await svc.session.commit()
        await svc.session.refresh(trade)
        return {
            "trade_id": trade.trade_id,
            "escrow_id": escrow.get("escrow_id"),
            "status": escrow.get("status", "pending"),
            "secret_hash": escrow.get("secret_hash", ""),
            "source_timelock": escrow.get("source_timelock", 0),
            "dest_timelock": escrow.get("dest_timelock", 0),
        }
    except Exception:
        await svc.session.rollback()
        # Release the claim marker so the trade can be retried — but only
        # back to the phase it held before this attempt.
        await _release_escrow_claim(svc, trade_id, prior_phase)
        logger.exception("Lock escrow failed for trade %s", trade_id)
        return JSONResponse(status_code=502, content={"error": "Lock escrow failed; no escrow was locked"})


@router.post("/v1/trading/trades/{trade_id}/settle")
async def settle_trade(
    trade_id: str,
    secret: Annotated[str, Body(embed=True)],
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # type: ignore[assignment]  # noqa: B008
):
    """Settle a trade by revealing the HTLC secret.

    Looks up the trade's escrow_id and calls the blockchain-node
    settlement RPC to reveal the secret and settle atomically on both
    chains. Updates the trade settlement_phase on success.

    Idempotent: if the trade is already completed, returns success without
    re-calling settle.
    """
    trade = await _lock_trade_for_update(svc, trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    if not trade.escrow_id:
        return JSONResponse(status_code=400, content={"error": "Trade has no escrow — lock escrow first"})
    # Idempotency: already settled — accept both the enum terminal value and
    # the legacy "completed" this router used to write (#1414).
    if trade.settlement_phase in {SettlementPhase.SETTLED.value, "completed"}:
        return {"trade_id": trade.trade_id, "escrow_id": trade.escrow_id, "result": "already_settled"}
    # #1415: terminal/invalid phases and dead trades must not settle — the
    # HTLC secret alone is not sufficient authorization.
    if trade.settlement_phase in {SettlementPhase.REFUNDED.value, SettlementPhase.DISPUTED.value} or trade.status in {
        "cancelled",
        "failed",
    }:
        return JSONResponse(
            status_code=409,
            content={"error": f"Trade cannot settle from status '{trade.status}' / phase '{trade.settlement_phase}'"},
        )
    # Claim-then-call (#1562): the committed 'settling' marker is the guard —
    # the settle RPC used to run with only the row lock, which is a no-op on
    # sqlite, so a crash between RPC success and commit left the phase
    # ambiguous and a retry could double-settle.
    prior_phase, refusal = await _claim_phase(
        svc,
        trade,
        trade_id,
        SettlementPhase.SETTLING,
        _SETTLE_CLAIM_TTL,
        "Settlement already in progress for this trade",
    )
    if refusal is not None:
        return refusal
    try:
        async with _get_settlement_client() as client:
            result = await client.settle(trade.escrow_id, secret)
        trade.settlement_phase = SettlementPhase.SETTLED.value
        await svc.session.commit()
        await svc.session.refresh(trade)
        return {"trade_id": trade.trade_id, "escrow_id": trade.escrow_id, "result": result}
    except Exception:
        await svc.session.rollback()
        # Release the claim marker so the trade can be retried — but only
        # back to the phase it held before this attempt.
        await _release_phase_claim(svc, trade_id, SettlementPhase.SETTLING, prior_phase)
        logger.exception("Settle trade failed for trade %s", trade_id)
        return JSONResponse(status_code=502, content={"error": "Settle trade failed; the trade was not settled"})


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
