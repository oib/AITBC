"""Transaction, block, and receipt endpoints for the Trading Service."""

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import get_logger
from aitbc.constants import BLOCKCHAIN_RPC_URL

from ..dependencies import get_session_dep
from ..domain.trading import TradeAgreement, TradeMatch, TradeRequest, TradeStatus, TradeType
from ..services.trading_service import TradingService

router = APIRouter(tags=["transactions"])
logger = get_logger(__name__)


async def _filtered_rows(session: AsyncSession, model, status_enum, type_enum):
    stmt = select(model)
    if status_enum is not None:
        stmt = stmt.where(model.status == status_enum.value)
    if type_enum is not None:
        stmt = stmt.where(model.trade_type == type_enum.value)
    stmt = stmt.order_by(model.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def _match_rows(session: AsyncSession, status_enum, type_enum):
    stmt = select(TradeMatch)
    if status_enum is not None:
        stmt = stmt.where(TradeMatch.status == status_enum.value)
    if type_enum is not None:
        stmt = stmt.join(TradeRequest, TradeMatch.request_id == TradeRequest.request_id).where(
            TradeRequest.trade_type == type_enum.value
        )
    stmt = stmt.order_by(TradeMatch.created_at)
    return list((await session.execute(stmt)).scalars().all())


def _serialize_request(r: TradeRequest) -> dict[str, Any]:
    return {
        "request_id": r.request_id,
        "action": "request",
        "buyer_agent_id": r.buyer_agent_id,
        "trade_type": r.trade_type,
        "status": r.status,
        "island_id": getattr(r, "island_id", None),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_match(m: TradeMatch) -> dict[str, Any]:
    return {
        "match_id": m.match_id,
        "action": "match",
        "request_id": m.request_id,
        "seller_agent_id": m.seller_agent_id,
        "status": m.status,
        "island_id": getattr(m, "island_id", None),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_agreement(a: TradeAgreement) -> dict[str, Any]:
    return {
        "agreement_id": a.agreement_id,
        "action": "agreement",
        "match_id": getattr(a, "match_id", None),
        "status": a.status,
        "island_id": getattr(a, "island_id", None),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/v1/transactions")
async def submit_transaction(transaction_data: dict[str, Any], session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Submit trading transaction."""
    transaction_type = transaction_data.get("type")
    action = transaction_data.get("action")
    if transaction_type != "trading":
        return JSONResponse(status_code=400, content={"error": "Invalid transaction type for Trading service"})
    try:
        svc = TradingService(session)
        if action == "request":
            request = await svc.create_request(transaction_data)
            transaction_id = request.request_id
        elif action == "match":
            match = await svc.create_match(transaction_data)
            transaction_id = match.match_id
        elif action == "agreement":
            agreement = await svc.create_agreement(transaction_data)
            transaction_id = agreement.agreement_id
        elif action == "settlement":
            settlement = await svc.create_settlement(transaction_data)
            transaction_id = settlement.settlement_id
        else:
            return JSONResponse(status_code=400, content={"error": f"Invalid action: {action}"})
        return {"status": "success", "transaction_id": transaction_id}
    except Exception:
        await session.rollback()
        logger.exception("Transaction submission error")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/v1/transactions")
async def get_transactions(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    transaction_type: str | None = None,
    action: str | None = None,
    status: str | None = None,
    island_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    """Query trading transactions."""
    try:
        status_enum = TradeStatus(status) if status else None
        type_enum = TradeType(transaction_type) if transaction_type else None
    except ValueError:
        return []

    fetchers = {
        "request": lambda: _filtered_rows(session, TradeRequest, status_enum, type_enum),
        "match": lambda: _match_rows(session, status_enum, type_enum),
        "agreement": lambda: _filtered_rows(session, TradeAgreement, status_enum, type_enum),
    }
    serializers = {"request": _serialize_request, "match": _serialize_match, "agreement": _serialize_agreement}

    try:
        wanted = [action] if action else list(fetchers)
        transactions = []
        for act in wanted:
            fetch, serialize = fetchers.get(act), serializers.get(act)
            if fetch is None:
                continue
            transactions.extend(serialize(row) for row in await fetch())
        if island_id:
            transactions = [t for t in transactions if t.get("island_id") == island_id]
        if offset:
            transactions = transactions[offset:]
        if limit is not None:
            transactions = transactions[:limit]
        return transactions
    except Exception:
        logger.exception("Transaction query error")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/v1/blocks")
async def get_blocks(limit: int | None = None, session: Annotated[AsyncSession | None, Depends(get_session_dep)] = None):
    """List recent blocks from the blockchain node RPC."""
    return await _fetch_blocks_from_chain(limit, chain_id=None)


@router.get("/v1/explorer/blocks")
async def get_blocks_v1(
    limit: int | None = None,
    chain_id: str | None = None,
    session: Annotated[AsyncSession | None, Depends(get_session_dep)] = None,
):
    """List recent blocks (v1/explorer path for CLI compatibility)."""
    return await _fetch_blocks_from_chain(limit, chain_id=chain_id)


@router.get("/api/v1/blocks")
async def get_blocks_api(
    limit: int | None = None,
    chain_id: str | None = None,
    session: Annotated[AsyncSession | None, Depends(get_session_dep)] = None,
):
    """List recent blocks (api/v1 path for CLI compatibility)."""
    return await _fetch_blocks_from_chain(limit, chain_id=chain_id)


async def _fetch_blocks_from_chain(limit: int | None, chain_id: str | None) -> dict[str, Any]:
    """Fetch recent blocks from the blockchain node RPC."""
    import httpx

    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL)
    actual_chain_id = chain_id or os.getenv("CHAIN_ID", "")
    actual_limit = min(limit or 50, 100)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            params: dict[str, Any] = {"limit": actual_limit}
            if actual_chain_id:
                params["chain_id"] = actual_chain_id
            resp = await client.get(f"{rpc_url}/rpc/blocks-range", params=params)
            if resp.status_code == 200:
                data = resp.json()
                blocks = data.get("blocks", [])
                return {
                    "blocks": blocks,
                    "limit": actual_limit,
                    "chain_id": actual_chain_id,
                    "total": len(blocks),
                }
            else:
                return {
                    "blocks": [],
                    "limit": actual_limit,
                    "chain_id": actual_chain_id,
                    "total": 0,
                    "error": f"Blockchain RPC returned {resp.status_code}",
                }
    except Exception as e:
        logger.error("Failed to fetch blocks from blockchain: %s", e)
        return {
            "blocks": [],
            "limit": actual_limit,
            "chain_id": actual_chain_id,
            "total": 0,
            "error": f"Blockchain RPC unavailable: {e}",
        }


@router.get("/v1/blocks/{block_id}")
def get_block(block_id: str, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Get block details."""
    return {"block_id": block_id, "error": "Block not found"}


@router.get("/v1/receipts")
def get_receipts(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    limit: int | None = None,
):
    """List job receipts."""
    return {"receipts": [], "limit": limit, "total": 0}


@router.get("/v1/explorer/receipts")
def get_receipts_v1(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    limit: int | None = None,
    job_id: str | None = None,
):
    """List job receipts (v1/explorer path for CLI compatibility)."""
    return {"receipts": [], "limit": limit, "job_id": job_id, "total": 0}


@router.get("/v1/transactions/{tx_hash}")
def get_transaction(tx_hash: str, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Get transaction details by hash."""
    return {"tx_hash": tx_hash, "error": "Transaction not found"}


@router.get("/v1/explorer/transactions/{tx_hash}")
def get_transaction_explorer(
    tx_hash: str,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
    chain_id: str | None = None,
):
    """Get transaction details by hash (explorer path for CLI compatibility)."""
    return {"tx_hash": tx_hash, "chain_id": chain_id or os.getenv("CHAIN_ID", ""), "error": "Transaction not found"}
