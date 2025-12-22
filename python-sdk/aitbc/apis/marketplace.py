"""
Marketplace API for AITBC Python SDK
"""

from typing import Dict, Any, Optional, List
import logging

from ..transport import Transport

logger = logging.getLogger(__name__)


class MarketplaceAPI:
    """Marketplace API client"""
    
    def __init__(self, transport: Transport):
        self.transport = transport
    
    async def list_offers(self, **params) -> List[Dict[str, Any]]:
        """List marketplace offers"""
        response = await self.transport.request('GET', '/v1/marketplace/offers', params=params)
        return response.get('offers', [])
    
    async def create_offer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new offer"""
        return await self.transport.request('POST', '/v1/marketplace/offers', data=data)
    
    async def get_offer(self, offer_id: str) -> Dict[str, Any]:
        """Get offer details"""
        return await self.transport.request('GET', f'/v1/marketplace/offers/{offer_id}')
    
    async def update_offer(self, offer_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update offer"""
        return await self.transport.request('PUT', f'/v1/marketplace/offers/{offer_id}', data=data)
    
    async def delete_offer(self, offer_id: str) -> None:
        """Delete offer"""
        await self.transport.request('DELETE', f'/v1/marketplace/offers/{offer_id}')
    
    async def accept_offer(self, offer_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Accept an offer"""
        return await self.transport.request('POST', f'/v1/marketplace/offers/{offer_id}/accept', data=data)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics"""
        return await self.transport.request('GET', '/v1/marketplace/stats')
