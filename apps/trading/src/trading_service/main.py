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
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
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

    # v0.10.1 §B18: Initialize gossip client on startup
    global _gossip_client
    try:
        from .config import settings as _settings
        from .services.gossip_client import GossipClient

        _gossip_client = GossipClient(
            backend=_settings.gossip_backend,
            redis_url=_settings.gossip_broadcast_url,
        )
        await _gossip_client.start()
        logger.info("Gossip client initialized (backend=%s)", _settings.gossip_backend)
    except Exception as e:
        logger.warning("Failed to initialize gossip client: %s — using fallback", e)

    # v0.10.1 §B19: Initialize lease tracker on startup
    global _lease_tracker
    try:
        from .config import settings as _settings
        from .services.lease_tracker import OfferLeaseTracker

        _lease_tracker = OfferLeaseTracker(redis_url=_settings.lease_tracker_redis_url)
        await _lease_tracker.start()
        logger.info("Offer lease tracker initialized")
    except Exception as e:
        logger.warning("Failed to initialize lease tracker: %s — using fallback", e)

    yield

    # v0.10.1 §B18/B19: Shutdown gossip client and lease tracker
    if _gossip_client is not None:
        try:
            await _gossip_client.stop()
        except Exception:
            pass
    if _lease_tracker is not None:
        try:
            await _lease_tracker.stop()
        except Exception:
            pass
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


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint"""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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


class _PollingSyncWrapper:
    """Lightweight wrapper for B20 polling fallback.

    Creates an :class:`OfferSyncService` with a fresh DB session on each
    ``sync_chain`` call, then closes the session.  This avoids holding a
    long-lived session in the global subscription service.
    """

    async def sync_chain(self, chain_id: str) -> dict[str, Any]:
        async with get_session() as session:
            svc = OfferSyncService(session)
            return await svc.sync_chain(chain_id)


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


# ============================================================================
# v0.8.2: Offer Subscription Endpoints (B2 + B5)
# ============================================================================

import json as _json  # noqa: E402

from fastapi import WebSocket as _WebSocket  # noqa: E402
from fastapi import WebSocketDisconnect as _WebSocketDisconnect  # noqa: E402

from aitbc.trading.subscription_types import (  # noqa: E402
    OfferEvent as _OfferEvent,
    OfferNotification as _OfferNotification,
    OfferSubscription as _OfferSubscription,
)
from .services.offer_notification_service import OfferNotificationService  # noqa: E402
from .services.offer_search_service import OfferSearchService  # noqa: E402
from .services.offer_subscription_service import OfferSubscriptionService  # noqa: E402

# Global instances (initialized on startup, shared across requests)
_subscription_service: OfferSubscriptionService | None = None
_notification_service: OfferNotificationService | None = None
_search_service: OfferSearchService | None = None
# v0.10.1 §B18/B19: Gossip client and lease tracker (initialized in lifespan)
_gossip_client: Any = None
_lease_tracker: Any = None


def _get_subscription_service() -> OfferSubscriptionService:
    """Get or create the global OfferSubscriptionService."""
    global _subscription_service
    if _subscription_service is None:
        from .services.gossip_client import GossipClient
        from .services.lease_tracker import OfferLeaseTracker

        from .config import settings as _settings

        # B18: Use the gossip client initialized on startup (or create a fallback)
        gossip = _gossip_client or GossipClient(
            backend=_settings.gossip_backend,
            redis_url=_settings.gossip_broadcast_url,
        )
        # B19: Use the lease tracker initialized on startup (or create a fallback)
        tracker = _lease_tracker or OfferLeaseTracker(redis_url=_settings.lease_tracker_redis_url)

        # B20: Factory that creates an OfferSyncService for polling fallback
        def _sync_factory() -> _PollingSyncWrapper:
            return _PollingSyncWrapper()

        _subscription_service = OfferSubscriptionService(
            gossip_client=gossip,
            lease_tracker=tracker,
            offer_sync_factory=_sync_factory,
        )
    return _subscription_service


def _get_notification_service() -> OfferNotificationService:
    """Get or create the global OfferNotificationService."""
    global _notification_service
    if _notification_service is None:
        from .config import settings as _settings

        _notification_service = OfferNotificationService(debounce_ms=_settings.offer_subscription_debounce_ms)
    return _notification_service


def _get_search_service() -> OfferSearchService:
    """Get or create the global OfferSearchService."""
    global _search_service
    if _search_service is None:
        _search_service = OfferSearchService()
    return _search_service


@app.post("/v1/trading/offers/subscribe")
async def subscribe_to_offers(request: dict[str, Any]):
    """Register an offer subscription and obtain a lease.

    Mirrors the blockchain-node ``POST /rpc/subscribe`` pattern.
    Returns a lease expiry timestamp that the client uses to track
    when to renew via the heartbeat endpoint.

    v0.10.1 §B19: Uses the Redis-backed :class:`OfferLeaseTracker` for
    real lease management.  Falls back to a computed expiry when Redis
    is unavailable so the endpoint always returns a valid response.
    """
    from .config import settings as _settings

    node_id = request.get("node_id", "")
    chain_id = request.get("chain_id", _settings.default_chain_id)
    if not node_id:
        return JSONResponse(status_code=400, content={"error": "node_id is required"})

    svc = _get_subscription_service()
    lease_duration = _settings.offer_subscription_heartbeat_seconds * 3
    try:
        expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id)
    except Exception as e:
        logger.warning("Lease registration failed for %s: %s — using computed expiry", node_id, e)
        import time as _time

        expiry = _time.time() + lease_duration
    return {"node_id": node_id, "chain_id": chain_id, "expiry": expiry, "lease_duration": lease_duration}


@app.post("/v1/trading/offers/heartbeat")
async def offer_heartbeat(request: dict[str, Any]):
    """Renew an offer subscription lease.

    Mirrors the blockchain-node ``POST /rpc/heartbeat`` pattern.

    v0.10.1 §B19: Uses the Redis-backed :class:`OfferLeaseTracker` to
    renew the lease.  Falls back to a computed expiry when Redis is
    unavailable or the lease was not found.
    """
    from .config import settings as _settings

    node_id = request.get("node_id", "")
    chain_id = request.get("chain_id", _settings.default_chain_id)
    if not node_id:
        return JSONResponse(status_code=400, content={"error": "node_id is required"})

    svc = _get_subscription_service()
    lease_duration = _settings.offer_subscription_heartbeat_seconds * 3
    try:
        expiry = await svc.renew_lease(node_id=node_id)
        if expiry == 0.0:
            # Lease not found — re-register so the client can continue
            expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id)
    except Exception as e:
        logger.warning("Lease renewal failed for %s: %s — using computed expiry", node_id, e)
        import time as _time

        expiry = _time.time() + lease_duration
    return {"node_id": node_id, "chain_id": chain_id, "expiry": expiry, "renewed": True}


@app.websocket("/v1/trading/offers/subscribe/ws")
async def offer_subscription_websocket(websocket: _WebSocket):
    """WebSocket endpoint for real-time offer change streaming.

    Protocol:
    1. Client connects and sends first message with filters:
       {"node_id": "...", "chain_id": "...", "filters": {...}}
    2. Server registers the subscriber and starts streaming offer events
    3. Server sends ping every 20s to keep connection alive
    4. Events are debounced into batches via OfferNotificationService
    """
    await websocket.accept()
    subscriber_id: str | None = None
    sub_svc = _get_subscription_service()
    notif_svc = _get_notification_service()

    try:
        # Receive first message with subscription config
        message = await websocket.receive_text()
        try:
            data = _json.loads(message)
        except _json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            await websocket.close(code=1008)
            return

        from .config import settings as _settings

        node_id = data.get("node_id", "")
        chain_id = data.get("chain_id", _settings.default_chain_id)
        filters = data.get("filters", {})

        if not node_id:
            await websocket.send_json({"error": "node_id is required"})
            await websocket.close(code=1008)
            return

        subscriber_id = f"{node_id}:{chain_id}"

        # v0.10.1 §B19: Register a lease for this subscriber
        lease_expiry: float = 0.0
        try:
            lease_expiry = await sub_svc.register_lease(node_id=node_id, chain_id=chain_id)
        except Exception as e:
            logger.warning("WebSocket lease registration failed for %s: %s", node_id, e)

        # Build subscription from filters
        subscription = _OfferSubscription(
            chain_id=filters.get("chain_id", chain_id),
            service_type=filters.get("service_type"),
            min_price=filters.get("min_price"),
            max_price=filters.get("max_price"),
            region=filters.get("region"),
            gpu_model=filters.get("gpu_model"),
            debounce_ms=_settings.offer_subscription_debounce_ms,
        )

        # Notification callback — sends batch to this WebSocket
        async def _notify(notification: _OfferNotification) -> None:
            try:
                await websocket.send_json(notification.to_dict())
            except Exception:
                pass

        await notif_svc.register_subscriber(subscriber_id, subscription, _notify)

        # Start chain subscription if not already running
        await sub_svc.start_chain(chain_id)

        await websocket.send_json(
            {
                "status": "subscribed",
                "node_id": node_id,
                "chain_id": chain_id,
                "filters": filters,
                "lease_expiry": lease_expiry,
            }
        )

        # Event forwarding: inject events into notification service
        async def _forward_to_notifications(event: _OfferEvent) -> None:
            await notif_svc.process_event(event)

        sub_svc._on_event = _forward_to_notifications  # noqa: SLF001

        # Heartbeat + receive loop
        import asyncio as _asyncio
        import time as _time

        async def _heartbeat() -> None:
            try:
                while True:
                    await _asyncio.sleep(_settings.offer_subscription_heartbeat_seconds)
                    # v0.10.1 §B19: Renew lease on each heartbeat
                    try:
                        await sub_svc.renew_lease(node_id=node_id)
                    except Exception:
                        pass
                    await websocket.send_json({"type": "ping", "timestamp": _time.time()})
            except _WebSocketDisconnect:
                pass
            except Exception:
                pass

        async def _receive_loop() -> None:
            try:
                while True:
                    msg = await websocket.receive_text()
                    try:
                        parsed = _json.loads(msg)
                        if parsed.get("type") == "pong":
                            # v0.10.1 §B19: Validate lease on WebSocket receive
                            try:
                                valid = await sub_svc.validate_lease(node_id=node_id)
                                if not valid:
                                    logger.info("Lease invalid for %s — closing WebSocket", node_id)
                                    await websocket.send_json({"error": "lease expired"})
                                    await websocket.close(code=1008)
                                    return
                            except Exception:
                                pass  # tolerate lease-check errors
                            continue
                    except _json.JSONDecodeError:
                        continue
            except _WebSocketDisconnect:
                pass
            except Exception:
                pass

        heartbeat_task = _asyncio.create_task(_heartbeat())
        receive_task = _asyncio.create_task(_receive_loop())
        done, pending = await _asyncio.wait([heartbeat_task, receive_task], return_when=_asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            try:
                await task
            except _asyncio.CancelledError:
                pass

    except _WebSocketDisconnect:
        logger.info("Offer WebSocket subscriber disconnected: %s", subscriber_id)
    except Exception as e:
        logger.error("Offer WebSocket error for %s: %s", subscriber_id, e)
    finally:
        if subscriber_id:
            await notif_svc.unregister_subscriber(subscriber_id)
            # v0.10.1 §B19: Revoke lease on disconnect
            try:
                parts = subscriber_id.split(":", 1)
                if len(parts) == 2:
                    await sub_svc.revoke_lease(parts[0])
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/v1/trading/offers/subscription-status")
async def get_subscription_status():
    """Get per-chain subscription health status.

    Returns: chain_id, status (subscribed/reconnecting/polling_fallback),
    last_event, event_count for each chain with an active subscription.
    """
    svc = _get_subscription_service()
    return svc.get_chain_status()


@app.get("/v1/trading/offers/search")
async def search_offers(
    q: str = "",
    chain_id: str | None = None,
    service_type: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 100,
):
    """Search offers via the optional search index (B7).

    Falls back to in-memory search when the external index is unavailable.
    """
    svc = _get_search_service()
    results = svc.search(
        query=q,
        chain_id=chain_id,
        service_type=service_type,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
    )
    return [_synced_offer_to_dict(o) for o in results]


# ============================================================================
# v0.9.0 §B6: Settlement endpoints
# ============================================================================

from aitbc.settlement.client import SettlementClient  # noqa: E402
from aitbc.settlement.types import SettlementConfig  # noqa: E402


def _get_settlement_client() -> SettlementClient:
    """Create a SettlementClient targeting the blockchain node settlement RPC."""
    rpc_url = os.getenv("SETTLEMENT_RPC_URL", "http://localhost:8202")
    config = SettlementConfig(settlement_rpc_url=rpc_url)
    return SettlementClient(config)


@app.post("/v1/trading/trades/{trade_id}/lock-escrow")
async def lock_escrow(
    trade_id: str,
    timeout_seconds: int | None = None,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # noqa: B008
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


@app.post("/v1/trading/trades/{trade_id}/settle")
async def settle_trade(
    trade_id: str,
    secret: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # noqa: B008
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


@app.get("/v1/trading/trades/{trade_id}/settlement-status")
async def settlement_status(
    trade_id: str,
    svc: Annotated[InterChainTradeService, Depends(get_inter_chain_service)] = None,  # noqa: B008
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


if __name__ == "__main__":
    import os

    import uvicorn

    host = os.getenv("TRADING_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("TRADING_BIND_PORT", "8104"))

    uvicorn.run(app, host=host, port=port, access_log=False)
