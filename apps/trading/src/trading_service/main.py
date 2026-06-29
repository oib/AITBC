"""
Trading Service main application
Manages trading operations
"""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

from .services.trading_service import TradingService
from .storage import get_session, init_db

configure_logging(level="INFO")
logger = get_logger(__name__)
BITCOIN_CONFIG = {
    "testnet": True,
    "main_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "exchange_rate": 100000,
    "min_confirmations": 1,
    "payment_timeout": 3600,
}
payments: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Trading Service."""
    logger.info("Starting Trading Service")
    await init_db()
    yield
    logger.info("Shutting down Trading Service")


app = FastAPI(title="AITBC Trading Service", description="Manages trading operations", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
app.add_middleware(ErrorHandlerMiddleware)


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """Get database session dependency"""
    async with get_session() as session:
        yield session


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="trading")


@app.get("/ready", response_model=None)
async def ready() -> dict[str, str] | JSONResponse:
    """Readiness check - verifies database connectivity"""
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "service": "trading"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        return JSONResponse(status_code=503, content={"status": "not_ready", "service": "trading", "error": str(e)})


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "trading"}


@app.get("/v1/trading/status")
async def trading_status() -> dict[str, str]:
    """Get trading status"""
    return {"status": "operational", "service": "trading", "message": "Trading service is running"}


async def get_trading_service(session: Annotated[AsyncSession, Depends(get_session_dep)]) -> TradingService:
    """Get trading service instance"""
    return TradingService(session)


@app.get("/v1/trading/requests")
async def get_requests(
    status: str | None,
    buyer_agent_id: str | None,
    trade_type: str | None,
    svc: Annotated[TradingService, Depends(get_trading_service)],
):
    """Get trade requests"""
    return await svc.list_requests(status=status, buyer_agent_id=buyer_agent_id, trade_type=trade_type)


@app.get("/v1/trading/requests/{request_id}")
async def get_request(request_id: str, svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Get a specific trade request"""
    return await svc.get_request(request_id)


@app.post("/v1/trading/requests")
async def create_request(request_data: dict[str, Any], svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Create a new trade request"""
    return await svc.create_request(request_data)


@app.get("/v1/trading/matches")
async def get_matches(
    status: str | None,
    buyer_agent_id: str | None,
    seller_agent_id: str | None,
    svc: Annotated[TradingService, Depends(get_trading_service)],
):
    """Get trade matches"""
    return await svc.list_matches(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/matches")
async def create_match(match_data: dict[str, Any], svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Create a new trade match"""
    return await svc.create_match(match_data)


@app.get("/v1/trading/agreements")
async def get_agreements(
    status: str | None,
    buyer_agent_id: str | None,
    seller_agent_id: str | None,
    svc: Annotated[TradingService, Depends(get_trading_service)],
):
    """Get trade agreements"""
    return await svc.list_agreements(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/agreements")
async def create_agreement(agreement_data: dict[str, Any], svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Create a new trade agreement"""
    return await svc.create_agreement(agreement_data)


@app.get("/v1/trading/analytics")
async def get_analytics(period_type: str | None, svc: Annotated[TradingService, Depends(get_trading_service)]):
    """Get trading analytics"""
    return await svc.get_analytics(period_type=period_type)


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict[str, Any], session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Submit trading transaction"""
    from .domain.trading import TradeAgreement, TradeMatch, TradeRequest, TradeSettlement

    transaction_type = transaction_data.get("type")
    action = transaction_data.get("action")
    if transaction_type != "trading":
        return ({"error": "Invalid transaction type for Trading service"}, 400)
    try:
        if action == "request":
            request = TradeRequest(**transaction_data)
            session.add(request)
        elif action == "match":
            match = TradeMatch(**transaction_data)
            session.add(match)
        elif action == "agreement":
            agreement = TradeAgreement(**transaction_data)
            session.add(agreement)
        elif action == "settlement":
            settlement = TradeSettlement(**transaction_data)
            session.add(settlement)
        else:
            return ({"error": f"Invalid action: {action}"}, 400)
        await session.commit()
        return {
            "status": "success",
            "transaction_id": transaction_data.get("request_id")
            or transaction_data.get("match_id")
            or transaction_data.get("agreement_id"),
        }
    except Exception as e:
        await session.rollback()
        logger.error("Transaction submission error: %s", e)
        return ({"error": str(e)}, 500)


@app.get("/v1/transactions")
async def get_transactions(
    transaction_type: str | None,
    action: str | None,
    status: str | None,
    island_id: str | None,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
):
    """Query trading transactions"""
    from sqlalchemy import select

    from .domain.trading import TradeAgreement, TradeMatch, TradeRequest

    try:
        transactions = []
        if action == "request" or not action:
            result = await session.execute(select(TradeRequest))
            requests = result.scalars().all()
            transactions.extend(
                [
                    {
                        "request_id": r.request_id,
                        "action": "request",
                        "buyer_agent_id": r.buyer_agent_id,
                        "trade_type": r.trade_type,
                        "status": r.status,
                        "island_id": r.island_id,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in requests
                ]
            )
        if action == "match" or not action:
            result = await session.execute(select(TradeMatch))
            matches = result.scalars().all()
            transactions.extend(
                [
                    {
                        "match_id": m.match_id,
                        "action": "match",
                        "request_id": m.request_id,
                        "seller_agent_id": m.seller_agent_id,
                        "status": m.status,
                        "island_id": m.island_id,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in matches
                ]
            )
        if action == "agreement" or not action:
            result = await session.execute(select(TradeAgreement))
            agreements = result.scalars().all()
            transactions.extend(
                [
                    {
                        "agreement_id": a.agreement_id,
                        "action": "agreement",
                        "match_id": a.match_id,
                        "status": a.status,
                        "island_id": a.island_id,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in agreements
                ]
            )
        if status:
            transactions = [t for t in transactions if t.get("status") == status]
        if island_id:
            transactions = [t for t in transactions if t.get("island_id") == island_id]
        return transactions
    except Exception as e:
        logger.error("Transaction query error: %s", e)
        return ({"error": str(e)}, 500)


@app.get("/v1/blocks")
async def get_blocks(limit: int | None, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """List recent blocks

    NOTE: Trading service is not production-critical.
    This endpoint returns placeholder data until trading service becomes production.
    In production, this would query blockchain RPC for actual block data.
    """
    return {"blocks": [], "limit": limit, "total": 0}


@app.get("/v1/explorer/blocks")
async def get_blocks_v1(limit: int | None, chain_id: str | None, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """List recent blocks (v1/explorer path for CLI compatibility)

    NOTE: Trading service is not production-critical.
    This endpoint returns placeholder data until trading service becomes production.
    In production, this would query blockchain RPC for actual block data.
    """
    return {"blocks": [], "limit": limit, "chain_id": chain_id or os.getenv("CHAIN_ID", ""), "total": 0}


@app.get("/api/v1/blocks")
async def get_blocks_api(limit: int | None, chain_id: str | None, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """List recent blocks (api/v1 path for CLI compatibility)"""
    return {"blocks": [], "limit": limit, "chain_id": chain_id or os.getenv("CHAIN_ID", ""), "total": 0}


@app.get("/v1/blocks/{block_id}")
async def get_block(block_id: str, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Get block details"""
    return {"block_id": block_id, "error": "Block not found"}


@app.get("/v1/receipts")
async def get_receipts(limit: int | None, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """List job receipts"""
    return {"receipts": [], "limit": limit, "total": 0}


@app.get("/v1/explorer/receipts")
async def get_receipts_v1(limit: int | None, job_id: str | None, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """List job receipts (v1/explorer path for CLI compatibility)"""
    return {"receipts": [], "limit": limit, "job_id": job_id, "total": 0}


@app.get("/v1/transactions/{tx_hash}")
async def get_transaction(tx_hash: str, session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Get transaction details by hash"""
    return {"tx_hash": tx_hash, "error": "Transaction not found"}


@app.get("/v1/explorer/transactions/{tx_hash}")
async def get_transaction_explorer(
    tx_hash: str, chain_id: str | None, session: Annotated[AsyncSession, Depends(get_session_dep)]
):
    """Get transaction details by hash (explorer path for CLI compatibility)"""
    return {"tx_hash": tx_hash, "chain_id": chain_id or os.getenv("CHAIN_ID", ""), "error": "Transaction not found"}


class ExchangePaymentRequest(BaseModel):
    """Exchange payment request schema"""

    user_id: str
    aitbc_amount: float
    btc_amount: float


@app.post("/v1/exchange/create-payment")
async def create_exchange_payment(
    payment_request: ExchangePaymentRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """Create a new Bitcoin payment request (migrated from Coordinator API)"""
    if payment_request.aitbc_amount <= 0 or payment_request.btc_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    expected_btc = payment_request.aitbc_amount / BITCOIN_CONFIG["exchange_rate"]
    if abs(payment_request.btc_amount - expected_btc) > 1e-08:
        raise HTTPException(status_code=400, detail="Amount mismatch")
    payment_id = str(uuid.uuid4())
    payment = {
        "payment_id": payment_id,
        "user_id": payment_request.user_id,
        "aitbc_amount": payment_request.aitbc_amount,
        "btc_amount": payment_request.btc_amount,
        "payment_address": BITCOIN_CONFIG["main_address"],
        "status": "pending",
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + BITCOIN_CONFIG["payment_timeout"],
        "confirmations": 0,
        "tx_hash": None,
    }
    payments[payment_id] = payment
    background_tasks.add_task(monitor_payment, payment_id)
    logger.info("Created exchange payment %s for user %s", payment_id, payment_request.user_id)
    return payment


@app.get("/v1/exchange/payment-status/{payment_id}")
async def get_exchange_payment_status(payment_id: str) -> dict[str, Any]:
    """Get payment status (migrated from Coordinator API)"""
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment = payments[payment_id]
    if payment["status"] == "pending" and time.time() > payment["expires_at"]:
        payment["status"] = "expired"
    return payment


@app.post("/v1/exchange/confirm-payment/{payment_id}")
async def confirm_exchange_payment(payment_id: str, tx_hash: str) -> dict[str, Any]:
    """Confirm payment (webhook from payment processor, migrated from Coordinator API)"""
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment = payments[payment_id]
    if payment["status"] != "pending":
        raise HTTPException(status_code=400, detail="Payment not in pending state")
    payment["status"] = "confirmed"
    payment["tx_hash"] = tx_hash
    payment["confirmed_at"] = int(time.time())
    try:
        logger.info("Minting %s AITBC tokens for user %s", payment["aitbc_amount"], payment["user_id"])
    except Exception as e:
        logger.error("Error minting tokens: %s", e)
    logger.info("Confirmed exchange payment %s with tx_hash %s", payment_id, tx_hash)
    return {"status": "ok", "payment_id": payment_id, "aitbc_amount": payment["aitbc_amount"]}


@app.get("/v1/exchange/rates")
async def get_exchange_rates() -> dict[str, Any]:
    """Get current exchange rates (migrated from Coordinator API)"""
    return {
        "btc_to_aitbc": BITCOIN_CONFIG["exchange_rate"],
        "aitbc_to_btc": 1.0 / BITCOIN_CONFIG["exchange_rate"],
        "fee_percent": 0.5,
    }


@app.get("/v1/exchange/market-stats")
async def get_market_stats() -> dict[str, Any]:
    """Get market statistics (migrated from Coordinator API)"""
    current_time = int(time.time())
    yesterday_time = current_time - 24 * 60 * 60
    daily_volume = 0
    for payment in payments.values():
        if payment["status"] == "confirmed" and payment.get("confirmed_at", 0) > yesterday_time:
            daily_volume += payment["aitbc_amount"]
    base_price = 1.0 / BITCOIN_CONFIG["exchange_rate"]
    price_change_percent = 5.2
    return {
        "price": base_price,
        "price_change_24h": price_change_percent,
        "daily_volume": daily_volume,
        "daily_volume_btc": daily_volume / BITCOIN_CONFIG["exchange_rate"],
        "total_payments": len([p for p in payments.values() if p["status"] == "confirmed"]),
        "pending_payments": len([p for p in payments.values() if p["status"] == "pending"]),
    }


@app.get("/v1/exchange/wallet/balance")
async def get_exchange_wallet_balance() -> dict[str, Any]:
    """Get Bitcoin wallet balance (migrated from Coordinator API)"""
    return {"balance": 0.0, "unconfirmed_balance": 0.0, "address": BITCOIN_CONFIG["main_address"]}


@app.get("/v1/exchange/wallet/info")
async def get_exchange_wallet_info() -> dict[str, Any]:
    """Get comprehensive wallet information (migrated from Coordinator API)"""
    return {"address": BITCOIN_CONFIG["main_address"], "network": "testnet", "balance": 0.0, "transactions": []}


async def monitor_payment(payment_id: str) -> None:
    """Monitor payment for confirmation (background task, migrated from Coordinator API)"""
    while payment_id in payments:
        payment = payments[payment_id]
        if payment["status"] == "pending" and time.time() > payment["expires_at"]:
            payment["status"] = "expired"
            logger.info("Payment %s expired", payment_id)
            break
        await asyncio.sleep(30)


# ============================================================================
# v0.8.0: Inter-Chain Trading Endpoints (B4 + B5)
# ============================================================================

from .services.chain_discovery import ChainDiscoveryService  # noqa: E402
from .services.inter_chain_service import InterChainTradeService  # noqa: E402
from .services.matching_engine import MatchingEngine  # noqa: E402


async def get_chain_discovery(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> ChainDiscoveryService:
    """Get chain discovery service instance."""
    from .clients.blockchain import BlockchainClient
    from .config import settings

    return ChainDiscoveryService(session, BlockchainClient(rpc_url=settings.blockchain_rpc_url))


async def get_inter_chain_service(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> InterChainTradeService:
    """Get inter-chain trade service instance."""
    return InterChainTradeService(session)


async def get_matching_engine(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> MatchingEngine:
    """Get matching engine instance."""
    return MatchingEngine(session)


# --- Chain Discovery Endpoints (B4) ---


@app.get("/v1/trading/chains")
async def list_chains(
    svc: Annotated[ChainDiscoveryService, Depends(get_chain_discovery)],
    status: str | None = None,
):
    """List registered chains for inter-chain trading."""
    return await svc.list_chains(status=status)


@app.post("/v1/trading/chains/register")
async def register_chain(
    chain_id: str,
    endpoint: str,
    svc: Annotated[ChainDiscoveryService, Depends(get_chain_discovery)],
):
    """Register a new chain in the island registry."""
    return await svc.register_chain(chain_id=chain_id, endpoint=endpoint)


@app.get("/v1/trading/chains/{chain_id}/health")
async def get_chain_health(
    chain_id: str,
    svc: Annotated[ChainDiscoveryService, Depends(get_chain_discovery)],
):
    """Get health metrics for a specific chain."""
    return await svc.get_chain_health(chain_id)


# --- Inter-Chain Trade Lifecycle Endpoints (B5) ---


@app.post("/v1/trading/inter-chain/create")
async def create_inter_chain_trade(
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
    source_chain: str,
    dest_chain: str,
    sender: str,
    recipient: str,
    amount: int,
    offer_id: str | None = None,
    price: float = 0.0,
    quantity: int = 0,
):
    """Create a new inter-chain trade."""
    return await svc.create_trade(
        source_chain=source_chain,
        dest_chain=dest_chain,
        sender=sender,
        recipient=recipient,
        amount=amount,
        offer_id=offer_id,
        price=price,
        quantity=quantity,
    )


@app.get("/v1/trading/inter-chain")
async def list_inter_chain_trades(
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
    status: str | None = None,
    source_chain: str | None = None,
    dest_chain: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List inter-chain trades with optional filters."""
    return await svc.list_trades(
        status=status,
        source_chain=source_chain,
        dest_chain=dest_chain,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/trading/inter-chain/{trade_id}")
async def get_inter_chain_trade(
    trade_id: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
):
    """Get inter-chain trade details."""
    trade = await svc.get_trade(trade_id)
    if not trade:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return trade


@app.get("/v1/trading/inter-chain/{trade_id}/status")
async def get_inter_chain_trade_status(
    trade_id: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
):
    """Get inter-chain trade status."""
    status = await svc.get_trade_status(trade_id)
    if not status:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return status


@app.get("/v1/trading/inter-chain/history")
async def get_inter_chain_trade_history(
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)],
    source_chain: str | None = None,
    dest_chain: str | None = None,
    limit: int = 50,
):
    """Get inter-chain trade history."""
    return await svc.get_trade_history(
        source_chain=source_chain,
        dest_chain=dest_chain,
        limit=limit,
    )


# --- Matching Engine Endpoint (B6) ---


@app.post("/v1/trading/inter-chain/{trade_id}/match")
async def match_inter_chain_trade(
    trade_id: str,
    svc: Annotated[MatchingEngine, Depends(get_matching_engine)],
):
    """Attempt to match an inter-chain trade with a counterparty."""
    result = await svc.match_trade(trade_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Trade not found"})
    return result


@app.post("/v1/trading/inter-chain/match-all")
async def match_all_pending_trades(
    svc: Annotated[MatchingEngine, Depends(get_matching_engine)],
):
    """Attempt to match all pending inter-chain trades."""
    return await svc.match_all_pending()


# ============================================================================
# v0.8.1: Cross-Chain Offer Sync Endpoints (B3 + B4)
# ============================================================================

from aitbc.trading.offer_types import (  # noqa: E402
    OfferDiscoveryRequest,
    OfferDiscoveryResult,
    OfferSyncStatusEntry,
)
from .services.offer_sync_service import OfferSyncService  # noqa: E402


async def get_offer_sync_service(
    session: Annotated[AsyncSession, Depends(get_session_dep)],
) -> OfferSyncService:
    """Get offer sync service instance."""
    return OfferSyncService(session)


def _synced_offer_to_dict(offer: Any) -> dict[str, Any]:
    """Convert a SyncedOffer to a dict for JSON response."""
    return offer.to_dict() if hasattr(offer, "to_dict") else dict(offer)


def _discovery_result_to_dict(result: OfferDiscoveryResult) -> dict[str, Any]:
    """Convert an OfferDiscoveryResult to a dict for JSON response."""
    return {
        "offers": [_synced_offer_to_dict(o) for o in result.offers],
        "total_count": result.total_count,
        "chains_searched": result.chains_searched,
        "stale_count": result.stale_count,
        "sync_triggered": result.sync_triggered,
    }


def _status_entry_to_dict(entry: OfferSyncStatusEntry) -> dict[str, Any]:
    """Convert an OfferSyncStatusEntry to a dict for JSON response."""
    return {
        "chain_id": entry.chain_id,
        "last_sync": entry.last_sync,
        "offer_count": entry.offer_count,
        "stale_count": entry.stale_count,
        "error_count": entry.error_count,
        "is_syncing": entry.is_syncing,
    }


# --- B3: Offer Discovery Endpoint ---


@app.post("/v1/trading/offers/discover")
async def discover_offers(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
    source_chain: str | None = None,
    dest_chain: str | None = None,
    service_type: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    region: str | None = None,
    gpu_model: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Discover offers across chains with filters.

    Queries the OfferCache. If cached offers are stale, triggers an
    on-demand sync before returning results.
    """
    request = OfferDiscoveryRequest(
        source_chain=source_chain,
        dest_chain=dest_chain,
        service_type=service_type,
        min_price=min_price,
        max_price=max_price,
        region=region,
        gpu_model=gpu_model,
        limit=limit,
        offset=offset,
    )
    result = await svc.discover_offers(request)
    return _discovery_result_to_dict(result)


# --- B4: Offer Sync Endpoints ---


@app.post("/v1/trading/offers/sync")
async def sync_offers(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
    chain_id: str | None = None,
    service_type: str | None = None,
    force: bool = False,
):
    """Trigger offer sync for a specific chain or all chains."""
    if chain_id:
        result = await svc.sync_chain(chain_id)
    else:
        results = await svc.sync_all_chains()
        result = {"results": results, "total_chains": len(results)}
    return result


@app.get("/v1/trading/offers/sync-status")
async def get_offer_sync_status(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
):
    """Get offer sync status per chain."""
    entries = svc.get_sync_status()
    return [_status_entry_to_dict(e) for e in entries]


@app.get("/v1/trading/offers/cache")
async def get_cached_offers(
    svc: Annotated[OfferSyncService, Depends(get_offer_sync_service)],
    chain_id: str | None = None,
    service_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
):
    """Get cached offers with optional filters."""
    offers = svc.get_cached_offers(
        chain_id=chain_id,
        service_type=service_type,
        status=status,
        limit=limit,
    )
    return [_synced_offer_to_dict(o) for o in offers]


if __name__ == "__main__":
    import os

    import uvicorn

    host = os.getenv("TRADING_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("TRADING_BIND_PORT", "8104"))

    uvicorn.run(app, host=host, port=port)
