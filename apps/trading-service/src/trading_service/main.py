"""
Trading Service main application
Manages trading operations
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc import (
    configure_logging,
    get_logger,
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

from .storage import init_db, get_session
from .services.trading_service import TradingService

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)


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
    return HealthResponse(status="healthy", service="trading-service")


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness check - verifies database connectivity"""
    try:
        async with get_session() as session:
            # Test database connection
            await session.execute("SELECT 1")
        return {"status": "ready", "service": "trading-service"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "trading-service", "error": str(e)},
        )


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "trading-service"}


@app.get("/trading/status")
async def trading_status() -> dict[str, str]:
    """Get trading status"""
    return {
        "status": "operational",
        "service": "trading-service",
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
    return svc.list_requests(status=status, buyer_agent_id=buyer_agent_id, trade_type=trade_type)


@app.get("/v1/trading/requests/{request_id}")
async def get_request(
    request_id: str,
    svc: TradingService = Depends(get_trading_service),
):
    """Get a specific trade request"""
    return svc.get_request(request_id)


@app.post("/v1/trading/requests")
async def create_request(
    request_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade request"""
    return svc.create_request(request_data)


@app.get("/v1/trading/matches")
async def get_matches(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade matches"""
    return svc.list_matches(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/matches")
async def create_match(
    match_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade match"""
    return svc.create_match(match_data)


@app.get("/v1/trading/agreements")
async def get_agreements(
    status: str | None = None,
    buyer_agent_id: str | None = None,
    seller_agent_id: str | None = None,
    svc: TradingService = Depends(get_trading_service),
):
    """Get trade agreements"""
    return svc.list_agreements(status=status, buyer_agent_id=buyer_agent_id, seller_agent_id=seller_agent_id)


@app.post("/v1/trading/agreements")
async def create_agreement(
    agreement_data: dict,
    svc: TradingService = Depends(get_trading_service),
):
    """Create a new trade agreement"""
    return svc.create_agreement(agreement_data)


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
    from .domain.trading import (
        TradeRequest, TradeMatch, TradeAgreement, TradeSettlement
    )
    
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
    from .domain.trading import TradeRequest, TradeMatch, TradeAgreement
    from sqlalchemy import select
    
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


@app.get("/blocks")
async def get_blocks(
    limit: int = 10,
    session: AsyncSession = Depends(get_session_dep),
):
    """List recent blocks"""
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
    """List recent blocks (v1/explorer path for CLI compatibility)"""
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


@app.get("/blocks/{block_id}")
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


@app.get("/receipts")
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


@app.get("/transactions/{tx_hash}")
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


@app.get("/explorer/transactions/{tx_hash}")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8104)
