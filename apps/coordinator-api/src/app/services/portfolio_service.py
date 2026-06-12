# mypy: ignore-errors
"""
Portfolio Service - Cross-wallet and cross-chain holdings aggregation

Aggregates:
- Wallet balances across all chains
- Staked amounts
- Active jobs/positions
- Transaction history
- Total portfolio value
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import httpx
from aitbc.aitbc_logging import get_logger
logger = get_logger(__name__)

@dataclass
class WalletHolding:
    """Holdings for a single wallet"""
    wallet_id: str
    address: str
    chain_id: str
    balance: int
    staked: int
    bridge_locked: int
    total_value_usd: float

@dataclass
class PortfolioPosition:
    """A position in the portfolio"""
    asset_type: str
    amount: int
    chain_id: str
    wallet_id: str
    usd_value: float
    details: dict[str, Any]

class PortfolioService:
    """
    Portfolio aggregation service.
    
    Aggregates holdings across:
    - Multiple wallets
    - Multiple chains
    - Staking positions
    - Active jobs/market positions
    """

    def __init__(self, wallet_service_url: str='http://localhost:8012', blockchain_rpc_url: str='http://localhost:8006', oracle_url: str='http://localhost:8203', session=None) -> None:
        self.wallet_service_url = wallet_service_url
        self.blockchain_rpc_url = blockchain_rpc_url
        self.oracle_url = oracle_url
        self.session = session
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def get_portfolio(self, user_id: str | None=None, wallet_addresses: list[str] | None=None) -> dict[str, Any]:
        """
        Get complete portfolio for a user or set of wallets.
        
        Args:
            user_id: User identifier (to fetch all user wallets)
            wallet_addresses: Specific wallet addresses to aggregate
        
        Returns:
            Portfolio summary with all positions
        """
        try:
            if user_id:
                wallets = await self._get_user_wallets(user_id)
            elif wallet_addresses:
                wallets = await self._get_wallets_by_address(wallet_addresses)
            else:
                return {'error': 'Must provide user_id or wallet_addresses'}
            if not wallets:
                return {'total_value_usd': 0, 'wallet_count': 0, 'positions': [], 'chains': []}
            positions = []
            chain_totals = {}
            total_native = 0
            total_staked = 0
            total_locked = 0
            for wallet in wallets:
                wallet_positions = await self._get_wallet_positions(wallet)
                positions.extend(wallet_positions)
                for pos in wallet_positions:
                    if pos.asset_type == 'native':
                        total_native += pos.amount
                    elif pos.asset_type == 'staked':
                        total_staked += pos.amount
                    elif pos.asset_type == 'bridge_locked':
                        total_locked += pos.amount
                    chain = pos.chain_id
                    if chain not in chain_totals:
                        chain_totals[chain] = {'native': 0, 'staked': 0, 'locked': 0}
                    chain_totals[chain][pos.asset_type] = chain_totals[chain].get(pos.asset_type, 0) + pos.amount
            token_price = await self._get_token_price('AITBC/USD')
            total_value_usd = (total_native + total_staked + total_locked) * token_price
            return {'total_value_usd': round(total_value_usd, 2), 'token_price_usd': token_price, 'wallet_count': len(wallets), 'positions': [{'asset_type': p.asset_type, 'amount': p.amount, 'chain_id': p.chain_id, 'wallet_id': p.wallet_id, 'usd_value': round(p.usd_value, 2), 'details': p.details} for p in positions], 'chains': [{'chain_id': chain, 'native': totals.get('native', 0), 'staked': totals.get('staked', 0), 'locked': totals.get('locked', 0), 'total': totals.get('native', 0) + totals.get('staked', 0) + totals.get('locked', 0)} for chain, totals in chain_totals.items()], 'summary': {'total_native': total_native, 'total_staked': total_staked, 'total_locked': total_locked, 'total_tokens': total_native + total_staked + total_locked}, 'timestamp': datetime.now(UTC).isoformat()}
        except Exception as e:
            logger.error('Portfolio aggregation failed: %s', e)
            return {'error': str(e), 'total_value_usd': 0}

    async def get_wallet_breakdown(self, address: str, chain_id: str='ait-mainnet') -> dict[str, Any]:
        """Get detailed breakdown for a single wallet"""
        try:
            response = await self._http_client.get(f'{self.blockchain_url}/rpc/accounts/{address}', params={'chain_id': chain_id})
            if response.status_code != 200:
                return {'error': 'Failed to fetch wallet data'}
            account_data = response.json()
            balance = account_data.get('balance', 0)
            staking_response = await self._http_client.get(f'{self.blockchain_url}/rpc/staking/{address}', params={'chain_id': chain_id})
            staked = 0
            if staking_response.status_code == 200:
                staking_data = staking_response.json()
                staked = staking_data.get('total_staked', 0)
            breakdown_response = await self._http_client.get(f'{self.blockchain_url}/rpc/balance/{address}', params={'chain_id': chain_id})
            bridge_locked = 0
            if breakdown_response.status_code == 200:
                breakdown = breakdown_response.json()
                bridge_locked = breakdown.get('bridge_locked', 0)
            token_price = await self._get_token_price('AITBC/USD')
            total_tokens = balance + staked + bridge_locked
            return {'address': address, 'chain_id': chain_id, 'available_balance': balance, 'staked': staked, 'bridge_locked': bridge_locked, 'total_tokens': total_tokens, 'total_value_usd': round(total_tokens * token_price, 2), 'token_price_usd': token_price, 'timestamp': datetime.now(UTC).isoformat()}
        except Exception as e:
            logger.error('Wallet breakdown failed for %s: %s', address, e)
            return {'error': str(e)}

    async def _get_user_wallets(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch all wallets for a user"""
        try:
            response = await self._http_client.get(f'{self.wallet_url}/wallets', headers={'X-User-ID': user_id})
            if response.status_code == 200:
                return response.json().get('wallets', [])
            return []
        except Exception as e:
            logger.warning('Failed to fetch user wallets: %s', e)
            return []

    async def _get_wallets_by_address(self, addresses: list[str]) -> list[dict[str, Any]]:
        """Fetch wallet details by addresses"""
        wallets = []
        for addr in addresses:
            wallets.append({'id': f'wallet_{addr[:16]}', 'address': addr, 'chain_id': 'ait-mainnet'})
        return wallets

    async def _get_wallet_positions(self, wallet: dict[str, Any]) -> list[PortfolioPosition]:
        """Get all positions for a wallet"""
        positions = []
        try:
            address = wallet.get('address')
            chain_id = wallet.get('chain_id', 'ait-mainnet')
            wallet_id = wallet.get('id', address)
            breakdown = await self.get_wallet_breakdown(address, chain_id)
            if 'error' in breakdown:
                return positions
            token_price = breakdown.get('token_price_usd', 0)
            if breakdown.get('available_balance', 0) > 0:
                positions.append(PortfolioPosition(asset_type='native', amount=breakdown['available_balance'], chain_id=chain_id, wallet_id=wallet_id, usd_value=breakdown['available_balance'] * token_price, details={'address': address}))
            if breakdown.get('staked', 0) > 0:
                positions.append(PortfolioPosition(asset_type='staked', amount=breakdown['staked'], chain_id=chain_id, wallet_id=wallet_id, usd_value=breakdown['staked'] * token_price, details={'address': address}))
            if breakdown.get('bridge_locked', 0) > 0:
                positions.append(PortfolioPosition(asset_type='bridge_locked', amount=breakdown['bridge_locked'], chain_id=chain_id, wallet_id=wallet_id, usd_value=breakdown['bridge_locked'] * token_price, details={'address': address}))
        except Exception as e:
            logger.warning('Failed to get positions for wallet %s: %s', wallet.get('id'), e)
        return positions

    async def _get_token_price(self, pair: str='AITBC/USD') -> float:
        """Get token price from oracle"""
        try:
            response = await self._http_client.get(f'{self.oracle_url}/oracle/price/{pair}', timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return data.get('price', 1.0)
            return 1.0
        except Exception as e:
            logger.warning('Failed to get token price: %s', e)
            return 1.0
_portfolio_service: PortfolioService | None = None

def get_portfolio_service() -> PortfolioService:
    """Get global portfolio service"""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service