# mypy: ignore-errors
"""
Trading Service main application
Manages trading operations
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
    configure_logging,
    get_logger,
)

from .services.trading_service import TradingService
from .storage import get_session, init_db

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)

# Exchange configuration (migrated from Coordinator API)
BITCOIN_CONFIG = {
    "testnet": True,
    "main_address": "tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",  # Testnet address
    "exchange_rate": 100000,  # 1 BTC = 100,000 AITBC
    "min_confirmations": 1,
    "payment_timeout": 3600,  # 1 hour
}

# In-memory storage for payments (migrated from Coordinator API)
payments: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Trading Service."""
    logger.info("Starting Trading Service")
    # Initialize database
    await init_db()
    yield
    logger.info("Shutting down Trading Service")


app = FastAPI(
    title="AITBC Trading Service",
    description="Manages trading operations",
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10*1024*1024)
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


@app.get("/ready")
async def ready() -> dict[str, str] | JSONResponse:
    """Readiness check - verifies database connectivity"""
    try:
        async with get_session() as session:
            # Test database connection
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "service": "trading"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "trading", "error": str(e)},
        )


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "trading"}


@app.get("/v1/trading/status")
async def trading_status() -> dict[str, str]:
    """Get trading status"""
    return {
        "status": "operational",
        "service": "trading",
        "message": "Trading service is running",
    }


async def get_trading_service(session: AsyncSession = Depends(get_session_dep)) -> TradingService:
    """Get trading service instance"""
    return TradingService(session)


@app.get("/v1/trading/requests")
async def get_requests(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    trade_type: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade requests"""
    return await svc.list_requests(status=status, buyer_agent_id=buyer_agent_id, trade_type=trade_type)


@app.get("/v1/trading/requests/{request_id}")
async def get_request(
    request_id: str,
    svc: TradingService = Depends(get_trading_service),
):
    """Get a specific trade request"""
    return await svc.get_request(request_id)


@app.post("/v1/trading/requests")
async def create_request(
    request_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade request"""
    return await svc.create_request(request_data)


@app.get("/v1/trading/matches")
async def get_matches(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade matches"""
    return await svc.list_matches(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/matches")
async def create_match(
    match_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade match"""
    return await svc.create_match(match_data)


@app.get("/v1/trading/agreements")
async def get_agreements(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade agreements"""
    return await svc.list_agreements(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/agreements")
async def create_agreement(
    agreement_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade agreement"""
    return await svc.create_agreement(agreement_data)


@app.get("/v1/trading/analytics")
async def get_analytics(
    period_type: str = "daily",
    svc: TradingService = Depends(get_trading_service),
):
    """Get trading analytics"""
    return await svc.get_analytics(period_type=period_type)


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict, session: AsyncSession = Depends(get_session_dep)):
    """Submit trading transaction"""
    from .domain.trading import TradeAgreement, TradeMatch, TradeRequest, TradeSettlement

    # Validate transaction type
    transaction_type = transaction_data.get('type')
    action = transaction_data.get('action')

    if transaction_type != 'trading':
        return {"error": "Invalid transaction type for Trading service"}, 400

    try:
        if action == 'request':
            request = TradeRequest(**transaction_data)
            session.add(request)
        elif action == 'match':
            match = TradeMatch(**transaction_data)
            session.add(match)
        elif action == 'agreement':
            agreement = TradeAgreement(**transaction_data)
            session.add(agreement)
        elif action == 'settlement':
            settlement = TradeSettlement(**transaction_data)
            session.add(settlement)
        else:
            return {"error": f"Invalid action: {action}"}, 400

        await session.commit()
        return {"status": "success", "transaction_id": transaction_data.get('request_id') or transaction_data.get('match_id') or transaction_data.get('agreement_id')}
    except Exception as e:
        await session.rollback()
        logger.error(f"Transaction submission error: {e}")
        return {"error": str(e)}, 500


@app.get("/v1/transactions")
async def get_transactions(
    transaction_type: str | None = None,
    action: str | None = None,
    status: str | None = None,
    island_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """Query trading transactions"""
    from sqlalchemy import select

    from .domain.trading import TradeAgreement, TradeMatch, TradeRequest

    try:
        transactions = []

        # Query based on action type
        if action == 'request' or not action:
            result = await session.execute(select(TradeRequest))
            requests = result.scalars().all()
            transactions.extend([{
                "request_id": r.request_id,
                "action": "request",
                "buyer_agent_id": r.buyer_agent_id,
                "trade_type": r.trade_type,
                "status": r.status,
                "island_id": r.island_id,
                "created_at": r.created_at.isoformat() if r.created_at else None
            } for r in requests])

        if action == 'match' or not action:
            result = await session.execute(select(TradeMatch))
            matches = result.scalars().all()
            transactions.extend([{
                "match_id": m.match_id,
                "action": "match",
                "request_id": m.request_id,
                "seller_agent_id": m.seller_agent_id,
                "status": m.status,
                "island_id": m.island_id,
                "created_at": m.created_at.isoformat() if m.created_at else None
            } for m in matches])

        if action == 'agreement' or not action:
            result = await session.execute(select(TradeAgreement))
            agreements = result.scalars().all()
            transactions.extend([{
                "agreement_id": a.agreement_id,
                "action": "agreement",
                "match_id": a.match_id,
                "status": a.status,
                "island_id": a.island_id,
                "created_at": a.created_at.isoformat() if a.created_at else None
            } for a in agreements])

        # Apply filters
        if status:
            transactions = [t for t in transactions if t.get('status') == status]
        if island_id:
            transactions = [t for t in transactions if t.get('island_id') == island_id]

        return transactions
    except Exception as e:
        logger.error(f"Transaction query error: {e}")
        return {"error": str(e)}, 500


@app.get("/v1/blocks")
async def get_blocks(
    limit: int = 10,
    session: AsyncSession = Depends(get_session_dep),
):
    """List recent blocks
    
    NOTE: Trading service is not production-critical. 
    This endpoint returns placeholder data until trading service becomes production.
    In production, this would query blockchain RPC for actual block data.
    """
    # Placeholder implementation - would query blockchain for blocks
    return {
        "blocks": [],
        "limit": limit,
        "total": 0
    }


@app.get("/v1/explorer/blocks")
async def get_blocks_v1(
    limit: int = 10,
    chain_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """List recent blocks (v1/explorer path for CLI compatibility)
    
    NOTE: Trading service is not production-critical.
    This endpoint returns placeholder data until trading service becomes production.
    In production, this would query blockchain RPC for actual block data.
    """
    # Placeholder implementation - would query blockchain for blocks
    return {
        "blocks": [],
        "limit": limit,
        "chain_id": chain_id or "ait-devnet",
        "total": 0
    }


@app.get("/api/v1/blocks")
async def get_blocks_api(
    limit: int = 10,
    chain_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """List recent blocks (api/v1 path for CLI compatibility)"""
    # Placeholder implementation - would query blockchain for blocks
    return {
        "blocks": [],
        "limit": limit,
        "chain_id": chain_id or "ait-devnet",
        "total": 0
    }


@app.get("/v1/blocks/{block_id}")
async def get_block(
    block_id: str,
    session: AsyncSession = Depends(get_session_dep),
):
    """Get block details"""
    # Placeholder implementation - would query blockchain for block
    return {
        "block_id": block_id,
        "error": "Block not found"
    }


@app.get("/v1/receipts")
async def get_receipts(
    limit: int = 10,
    session: AsyncSession = Depends(get_session_dep),
):
    """List job receipts"""
    # Placeholder implementation - would query database for receipts
    return {
        "receipts": [],
        "limit": limit,
        "total": 0
    }


@app.get("/v1/explorer/receipts")
async def get_receipts_v1(
    limit: int = 10,
    job_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """List job receipts (v1/explorer path for CLI compatibility)"""
    # Placeholder implementation - would query database for receipts
    return {
        "receipts": [],
        "limit": limit,
        "job_id": job_id,
        "total": 0
    }


@app.get("/v1/transactions/{tx_hash}")
async def get_transaction(
    tx_hash: str,
    session: AsyncSession = Depends(get_session_dep),
):
    """Get transaction details by hash"""
    # Placeholder implementation - would query blockchain for transaction
    return {
        "tx_hash": tx_hash,
        "error": "Transaction not found"
    }


@app.get("/v1/explorer/transactions/{tx_hash}")
async def get_transaction_explorer(
    tx_hash: str,
    chain_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """Get transaction details by hash (explorer path for CLI compatibility)"""
    # Placeholder implementation - would query blockchain for transaction
    return {
        "tx_hash": tx_hash,
        "chain_id": chain_id or "ait-devnet",
        "error": "Transaction not found"
    }


# ===== Exchange Endpoints (Migrated from Coordinator API) =====

class ExchangePaymentRequest(BaseModel):
    """Exchange payment request schema"""
    user_id: str
    aitbc_amount: float
    btc_amount: float


@app.post("/v1/exchange/create-payment")
async def create_exchange_payment(
    payment_request: ExchangePaymentRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Create a new Bitcoin payment request (migrated from Coordinator API)"""
    
    # Validate request
    if payment_request.aitbc_amount <= 0 or payment_request.btc_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    
    # Calculate expected BTC amount
    expected_btc = payment_request.aitbc_amount / BITCOIN_CONFIG["exchange_rate"]
    
    # Allow small difference for rounding
    if abs(payment_request.btc_amount - expected_btc) > 0.00000001:
        raise HTTPException(status_code=400, detail="Amount mismatch")
    
    # Create payment record
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
    
    # Store payment
    payments[payment_id] = payment
    
    # Start payment monitoring in background
    background_tasks.add_task(monitor_payment, payment_id)
    
    logger.info(f"Created exchange payment {payment_id} for user {payment_request.user_id}")
    return payment


@app.get("/v1/exchange/payment-status/{payment_id}")
async def get_exchange_payment_status(payment_id: str) -> dict[str, Any]:
    """Get payment status (migrated from Coordinator API)"""
    
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment = payments[payment_id]
    
    # Check if expired
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
    
    # Verify transaction (in production, verify with blockchain API)
    # For demo, we'll accept any tx_hash
    
    payment["status"] = "confirmed"
    payment["tx_hash"] = tx_hash
    payment["confirmed_at"] = int(time.time())
    
    # Mint AITBC tokens to user's wallet
    try:
        # Placeholder for token minting - would call blockchain service
        logger.info(f"Minting {payment['aitbc_amount']} AITBC tokens for user {payment['user_id']}")
    except Exception as e:
        logger.error(f"Error minting tokens: {e}")
        # In production, handle this error properly
    
    logger.info(f"Confirmed exchange payment {payment_id} with tx_hash {tx_hash}")
    return {"status": "ok", "payment_id": payment_id, "aitbc_amount": payment["aitbc_amount"]}


@app.get("/v1/exchange/rates")
async def get_exchange_rates() -> dict[str, Any]:
    """Get current exchange rates (migrated from Coordinator API)"""
    
    return {
        "btc_to_aitbc": BITCOIN_CONFIG["exchange_rate"],
        "aitbc_to_btc": 1.0 / BITCOIN_CONFIG["exchange_rate"],
        "fee_percent": 0.5
    }


@app.get("/v1/exchange/market-stats")
async def get_market_stats() -> dict[str, Any]:
    """Get market statistics (migrated from Coordinator API)"""
    
    # Calculate 24h volume from payments
    current_time = int(time.time())
    yesterday_time = current_time - 24 * 60 * 60  # 24 hours ago
    
    daily_volume = 0
    for payment in payments.values():
        if payment["status"] == "confirmed" and payment.get("confirmed_at", 0) > yesterday_time:
            daily_volume += payment["aitbc_amount"]
    
    # Calculate price change (simulated)
    base_price = 1.0 / BITCOIN_CONFIG["exchange_rate"]
    price_change_percent = 5.2  # Simulated +5.2%
    
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
    # Placeholder implementation - would query wallet service
    return {
        "balance": 0.0,
        "unconfirmed_balance": 0.0,
        "address": BITCOIN_CONFIG["main_address"]
    }


@app.get("/v1/exchange/wallet/info")
async def get_exchange_wallet_info() -> dict[str, Any]:
    """Get comprehensive wallet information (migrated from Coordinator API)"""
    # Placeholder implementation - would query wallet service
    return {
        "address": BITCOIN_CONFIG["main_address"],
        "network": "testnet",
        "balance": 0.0,
        "transactions": []
    }


async def monitor_payment(payment_id: str) -> None:
    """Monitor payment for confirmation (background task, migrated from Coordinator API)"""
    
    while payment_id in payments:
        payment = payments[payment_id]
        
        # Check if expired
        if payment["status"] == "pending" and time.time() > payment["expires_at"]:
            payment["status"] = "expired"
            logger.info(f"Payment {payment_id} expired")
            break
        
        # In production, check blockchain for payment
        # For demo, we'll wait for manual confirmation
        
        await asyncio.sleep(30)  # Check every 30 seconds


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8104)
