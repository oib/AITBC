"""
Portfolio Aggregation Service
Aggregates portfolio data from wallet, exchange, marketplace, trading, and AI services
"""
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from aitbc import get_logger

logger = get_logger(__name__)

class PortfolioAggregationService:
    """Service to aggregate portfolio data from multiple AITBC services"""

    def __init__(self) -> None:
        self.wallet_service_url = 'http://localhost:8003'
        self.exchange_service_url = 'http://localhost:8203'
        self.marketplace_service_url = 'http://localhost:8102'
        self.trading_service_url = 'http://localhost:8104'
        self.ai_service_url = 'http://localhost:8005'
        verify_ssl = os.getenv('VERIFY_SSL', 'true').lower() == 'true'
        self.http_client = httpx.AsyncClient(timeout=10.0, verify=verify_ssl)

    async def get_unified_portfolio(self, agent_address: str | None=None) -> dict[str, Any]:
        """
        Get unified portfolio view by aggregating data from all services

        Args:
            agent_address: Optional agent address to filter portfolio data

        Returns:
            Unified portfolio data containing wallet balances, exchange rates,
            marketplace stats, trading analytics, and AI signals
        """
        try:
            wallet_data = await self._get_wallet_balances(agent_address)
            exchange_data = await self._get_exchange_rates()
            marketplace_data = await self._get_marketplace_stats()
            trading_data = await self._get_trading_analytics(agent_address)
            ai_data = await self._get_ai_trade_signals()
            portfolio_summary = self._calculate_portfolio_summary(wallet_data, exchange_data, marketplace_data, trading_data, ai_data)
            return {'timestamp': datetime.now(UTC).isoformat(), 'agent_address': agent_address, 'wallet': wallet_data, 'exchange': exchange_data, 'marketplace': marketplace_data, 'trading': trading_data, 'ai_signals': ai_data, 'summary': portfolio_summary}
        except Exception as e:
            logger.error('Error aggregating portfolio data: %s', str(e))
            raise

    async def _get_wallet_balances(self, agent_address: str | None=None) -> dict[str, Any]:
        """Fetch wallet balances from wallet service"""
        try:
            response = await self.http_client.get(f'{self.wallet_service_url}/v1/wallets')
            if response.status_code == 200:
                data = response.json()
                wallets = data.get('items', [])
                if agent_address:
                    wallets = [w for w in wallets if w.get('public_key') == agent_address or w.get('wallet_name') == agent_address]
                total_balance = len(wallets)
                return {'wallets': wallets, 'total_wallets': len(wallets), 'total_balance': total_balance}
            else:
                logger.warning('Wallet service returned status %s', response.status_code)
                return {'wallets': [], 'total_wallets': 0, 'total_balance': 0, 'error': 'Wallet service unavailable'}
        except Exception as e:
            logger.error('Error fetching wallet balances: %s', str(e))
            return {'wallets': [], 'total_wallets': 0, 'total_balance': 0, 'error': str(e)}

    async def _get_exchange_rates(self) -> dict[str, Any]:
        """Fetch exchange rates from exchange service"""
        try:
            response = await self.http_client.get(f'{self.exchange_service_url}/v1/exchange/rates')
            if response.status_code == 200:
                return dict(response.json())
            else:
                logger.warning('Exchange service returned status %s', response.status_code)
                return {'rates': {}, 'error': 'Exchange service unavailable'}
        except Exception as e:
            logger.error('Error fetching exchange rates: %s', str(e))
            return {'rates': {}, 'error': str(e)}

    async def _get_marketplace_stats(self) -> dict[str, Any]:
        """Fetch marketplace statistics from marketplace service"""
        try:
            response = await self.http_client.get(f'{self.marketplace_service_url}/v1/marketplace/analytics?period_type=daily')
            if response.status_code == 200:
                data = response.json()
                return {'offers': data.get('total_offers', 0), 'bids': data.get('total_bids', 0), 'capacity': data.get('total_capacity', 0), 'analytics': data}
            else:
                logger.warning('Marketplace service returned status %s', response.status_code)
                return {'offers': 0, 'bids': 0, 'capacity': 0, 'error': 'Marketplace service unavailable'}
        except Exception as e:
            logger.error('Error fetching marketplace stats: %s', str(e))
            return {'offers': 0, 'bids': 0, 'capacity': 0, 'error': str(e)}

    async def _get_trading_analytics(self, agent_address: str | None=None) -> dict[str, Any]:
        """Fetch trading analytics from trading service"""
        try:
            url = f'{self.trading_service_url}/v1/trading/analytics'
            if agent_address:
                url += f'?agent_address={agent_address}'
            response = await self.http_client.get(url)
            if response.status_code == 200:
                return dict(response.json())
            else:
                logger.warning('Trading service returned status %s', response.status_code)
                return {'trades': [], 'analytics': {}, 'error': 'Trading service unavailable'}
        except Exception as e:
            logger.error('Error fetching trading analytics: %s', str(e))
            return {'trades': [], 'analytics': {}, 'error': str(e)}

    async def _get_ai_trade_signals(self) -> dict[str, Any]:
        """Fetch AI trade signals from AI service"""
        try:
            response = await self.http_client.post(f'{self.ai_service_url}/api/ai/trade', json={'symbol': 'AITBC/BTC', 'strategy': 'ai_enhanced'})
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success' and 'decision' in data:
                    decision = data['decision']
                    return {'signals': [{'symbol': decision.get('symbol'), 'signal': decision.get('signal'), 'confidence': decision.get('confidence'), 'price': decision.get('price'), 'reasoning': decision.get('reasoning'), 'timestamp': decision.get('timestamp')}]}
                else:
                    return {'signals': [], 'error': 'Invalid response format'}
            else:
                logger.warning('AI service returned status %s', response.status_code)
                return {'signals': [], 'error': 'AI service unavailable'}
        except Exception as e:
            logger.error('Error fetching AI signals: %s', str(e))
            return {'signals': [], 'error': str(e)}

    def _calculate_portfolio_summary(self, wallet_data: dict[str, Any], exchange_data: dict[str, Any], marketplace_data: dict[str, Any], trading_data: dict[str, Any], ai_data: dict[str, Any]) -> dict[str, Any]:
        """Calculate portfolio summary metrics from aggregated data"""
        try:
            total_aitbc_balance = 0.0
            wallets = wallet_data.get('wallets', [])
            total_aitbc_balance = wallet_data.get('total_balance', len(wallets))
            rates = exchange_data.get('rates', {})
            aitbc_btc_rate = rates.get('BTC/AITBC', {}).get('rate', 1e-05)
            btc_value = total_aitbc_balance * aitbc_btc_rate
            marketplace_offers = marketplace_data.get('offers', 0)
            marketplace_bids = marketplace_data.get('bids', 0)
            marketplace_capacity = marketplace_data.get('capacity', 0)
            trading_analytics = trading_data.get('analytics', {})
            total_trades = trading_analytics.get('total_trades', 0)
            completed_trades = trading_analytics.get('completed_trades', 0)
            success_rate = completed_trades / total_trades * 100 if total_trades > 0 else 0
            signals = ai_data.get('signals', [])
            avg_signal_confidence = 0.0
            if signals:
                avg_signal_confidence = sum(s.get('confidence', 0) for s in signals) / len(signals)
            return {'total_aitbc_balance': total_aitbc_balance, 'btc_equivalent': btc_value, 'exchange_rate': aitbc_btc_rate, 'marketplace_exposure': {'offers': marketplace_offers, 'bids': marketplace_bids, 'capacity': marketplace_capacity}, 'trading_performance': {'total_trades': total_trades, 'completed_trades': completed_trades, 'success_rate': success_rate}, 'ai_signal_summary': {'total_signals': len(signals), 'average_confidence': avg_signal_confidence}}
        except Exception as e:
            logger.error('Error calculating portfolio summary: %s', str(e))
            return {'total_aitbc_balance': 0, 'btc_equivalent': 0, 'exchange_rate': 0, 'error': str(e)}

    async def close(self) -> None:
        """Close HTTP client"""
        await self.http_client.aclose()
