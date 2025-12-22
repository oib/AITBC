"""
Receipts API for AITBC Python SDK
"""

from typing import Dict, Any, Optional, List
import logging

from ..transport import Transport

logger = logging.getLogger(__name__)


class ReceiptsAPI:
    """Receipts API client"""
    
    def __init__(self, transport: Transport):
        self.transport = transport
    
    async def get(self, job_id: str) -> Dict[str, Any]:
        """Get job receipt"""
        return await self.transport.request('GET', f'/v1/receipts/{job_id}')
    
    async def verify(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        """Verify receipt"""
        return await self.transport.request('POST', '/v1/receipts/verify', data=receipt)
    
    async def list(self, **params) -> List[Dict[str, Any]]:
        """List receipts"""
        response = await self.transport.request('GET', '/v1/receipts', params=params)
        return response.get('receipts', [])
    
    async def stream(self, **params):
        """Stream new receipts"""
        return self.transport.stream('GET', '/v1/receipts/stream', params=params)
