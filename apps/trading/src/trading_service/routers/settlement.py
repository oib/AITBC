"""Settlement endpoints for the Trading Service."""

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.settlement.client import SettlementClient
from aitbc.settlement.types import SettlementConfig

from ..dependencies import get_inter_chain_service
from ..services.inter_chain_service import InterChainTradeService

router = APIRouter(tags=["settlement"])
logger = get_logger(__name__)


def _get_settlement_client() -> SettlementClient:
    """Create a SettlementClient targeting the blockchain node settlement RPC."""
    rpc_url = os.getenv("SETTLEMENT_RPC_URL", BLOCKCHAIN_RPC_URL)
    config = SettlementConfig(settlement_rpc_url=rpc_url)
    return SettlementClient(config)


@router.post("/v1/trading/trades/{trade_id}/lock-escrow")
async def lock_escrow(
    trade_id: str,
    timeout_seconds: int | None = None,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # type: ignore[assignment]  # noqa: B008
):
    """Initiate escrow lock for a trade.

    Looks up the inter-chain trade, extracts source/dest chain, sender,
    recipient, and amount, then calls the blockchain-node settlement RPC
    to create a cross-chain escrow. Persists the returned escrow_id,
    secret_hash, and timelocks on the trade record.
    """
    trade = await svc.get_trade(trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
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
        trade.settlement_phase = "pending"
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
    except Exception as e:
        logger.error("Lock escrow failed for trade %s: %s", trade_id, e)
        return JSONResponse(status_code=502, content={"error": f"Lock escrow failed: {e}"})


@router.post("/v1/trading/trades/{trade_id}/settle")
async def settle_trade(
    trade_id: str,
    secret: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # type: ignore[assignment]  # noqa: B008
):
    """Settle a trade by revealing the HTLC secret.

    Looks up the trade's escrow_id and calls the blockchain-node
    settlement RPC to reveal the secret and settle atomically on both
    chains. Updates the trade settlement_phase on success.
    """
    trade = await svc.get_trade(trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    if not trade.escrow_id:
        return JSONResponse(status_code=400, content={"error": "Trade has no escrow — lock escrow first"})
    try:
        async with _get_settlement_client() as client:
            result = await client.settle(trade.escrow_id, secret)
        trade.settlement_phase = "completed"
        await svc.session.commit()
        await svc.session.refresh(trade)
        return {"trade_id": trade.trade_id, "escrow_id": trade.escrow_id, "result": result}
    except Exception as e:
        logger.error("Settle trade failed for trade %s: %s", trade_id, e)
        return JSONResponse(status_code=502, content={"error": f"Settle trade failed: {e}"})


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
    response: dict[str, Any] = {
        "trade_id": trade.trade_id,
        "settlement_phase": trade.settlement_phase,
        "escrow_id": trade.escrow_id,
    }
    if trade.escrow_id:
        try:
            async with _get_settlement_client() as client:
                escrow_status = await client.get_escrow_status(trade.escrow_id)
            response["escrow_status"] = escrow_status
        except Exception as e:
            logger.error("Get settlement status failed for trade %s: %s", trade_id, e)
            response["escrow_status"] = "unknown"
            response["error"] = str(e)
    return response
