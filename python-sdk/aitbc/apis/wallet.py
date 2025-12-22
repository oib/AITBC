"""
Wallet API for AITBC Python SDK
"""

from typing import Dict, Any, Optional, List
import logging

from ..transport import Transport

logger = logging.getLogger(__name__)


class WalletAPI:
    """Wallet API client"""
    
    def __init__(self, transport: Transport):
        self.transport = transport
    
    async def create(self) -> Dict[str, Any]:
        """Create a new wallet"""
        return await self.transport.request('POST', '/v1/wallet')
    
    async def get_balance(self, token: Optional[str] = None) -> Dict[str, Any]:
        """Get wallet balance"""
        params = {}
        if token:
            params['token'] = token
        return await self.transport.request('GET', '/v1/wallet/balance', params=params)
    
    async def send(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send tokens"""
        return await self.transport.request('POST', '/v1/wallet/send', data=data)
    
    async def get_address(self) -> str:
        """Get wallet address"""
        response = await self.transport.request('GET', '/v1/wallet/address')
        return response.get('address')
    
    async def get_transactions(self, **params) -> List[Dict[str, Any]]:
        """Get transaction history"""
        response = await self.transport.request('GET', '/v1/wallet/transactions', params=params)
        return response.get('transactions', [])
    
    async def stake(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Stake tokens"""
        return await self.transport.request('POST', '/v1/wallet/stake', data=data)
    
    async def unstake(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Unstake tokens"""
        return await self.transport.request('POST', '/v1/wallet/unstake', data=data)
