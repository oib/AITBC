"""
Portfolio Management API Endpoints
REST API for unified portfolio management across AITBC services
"""
from datetime import UTC
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from aitbc import get_logger
from aitbc.rate_limiting import rate_limit
from ....services.portfolio_aggregation_service import PortfolioAggregationService
logger = get_logger(__name__)
router = APIRouter(prefix='/portfolio', tags=['portfolio'])
portfolio_service = PortfolioAggregationService()

class PortfolioSummaryResponse(BaseModel):
    """Response model for unified portfolio summary"""
    timestamp: str
    agent_address: str | None
    wallet: dict
    exchange: dict
    marketplace: dict
    trading: dict
    ai_signals: dict
    summary: dict

class PortfolioHealthResponse(BaseModel):
    """Response model for portfolio health check"""
    status: str
    services: dict[str, str]
    timestamp: str

@router.get('/unified', response_model=PortfolioSummaryResponse)
@rate_limit(rate=100, per=60)
async def get_unified_portfolio(request: Request, agent_address: str | None=Query(default=None, description='Filter by agent address')) -> PortfolioSummaryResponse:
    """
    Get unified portfolio view aggregating data from all AITBC services
    
    Aggregates data from:
    - Wallet service (8003): Wallet balances
    - Exchange service (8011): Exchange rates
    - Marketplace service (8102): Marketplace stats
    - Trading service (8104): Trading analytics
    - AI service (8005): AI trade signals
    """
    try:
        portfolio_data = await portfolio_service.get_unified_portfolio(agent_address)
        return PortfolioSummaryResponse(**portfolio_data)
    except Exception as e:
        logger.error('Error getting unified portfolio: %s', str(e))
        raise HTTPException(status_code=500, detail=f'Failed to get portfolio data: {str(e)}')

@router.get('/health', response_model=PortfolioHealthResponse)
@rate_limit(rate=200, per=60)
async def get_portfolio_health(request: Request) -> PortfolioHealthResponse:
    """Health check for portfolio aggregation service and dependencies"""
    services_status = {}
    overall_status = 'healthy'
    try:
        wallet_data = await portfolio_service._get_wallet_balances()
        services_status['wallet'] = 'healthy' if not wallet_data.get('error') else 'degraded'
        if wallet_data.get('error'):
            overall_status = 'degraded'
    except Exception:
        services_status['wallet'] = 'unhealthy'
        overall_status = 'degraded'
    try:
        exchange_data = await portfolio_service._get_exchange_rates()
        services_status['exchange'] = 'healthy' if not exchange_data.get('error') else 'degraded'
        if exchange_data.get('error'):
            overall_status = 'degraded'
    except Exception:
        services_status['exchange'] = 'unhealthy'
        overall_status = 'degraded'
    try:
        marketplace_data = await portfolio_service._get_marketplace_stats()
        services_status['marketplace'] = 'healthy' if not marketplace_data.get('error') else 'degraded'
        if marketplace_data.get('error'):
            overall_status = 'degraded'
    except Exception:
        services_status['marketplace'] = 'unhealthy'
        overall_status = 'degraded'
    try:
        trading_data = await portfolio_service._get_trading_analytics()
        services_status['trading'] = 'healthy' if not trading_data.get('error') else 'degraded'
        if trading_data.get('error'):
            overall_status = 'degraded'
    except Exception:
        services_status['trading'] = 'unhealthy'
        overall_status = 'degraded'
    try:
        ai_data = await portfolio_service._get_ai_trade_signals()
        services_status['ai'] = 'healthy' if not ai_data.get('error') else 'degraded'
        if ai_data.get('error'):
            overall_status = 'degraded'
    except Exception:
        services_status['ai'] = 'unhealthy'
        overall_status = 'degraded'
    from datetime import datetime
    return PortfolioHealthResponse(status=overall_status, services=services_status, timestamp=datetime.now(UTC).isoformat())

@router.get('/summary')
@rate_limit(rate=200, per=60)
async def get_portfolio_summary_only(request: Request, agent_address: str | None=Query(default=None, description='Filter by agent address')) -> dict:
    """Get only the portfolio summary metrics without full details"""
    try:
        portfolio_data = await portfolio_service.get_unified_portfolio(agent_address)
        return {'timestamp': portfolio_data['timestamp'], 'agent_address': agent_address, 'summary': portfolio_data['summary']}
    except Exception as e:
        logger.error('Error getting portfolio summary: %s', str(e))
        raise HTTPException(status_code=500, detail=f'Failed to get portfolio summary: {str(e)}')