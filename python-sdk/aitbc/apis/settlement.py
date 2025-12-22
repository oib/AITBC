"""
Settlement API for AITBC Python SDK
"""

from typing import Dict, Any, Optional, List
import logging

from ..transport import Transport
from ..transport.multinetwork import MultiNetworkClient

logger = logging.getLogger(__name__)


class SettlementAPI:
    """Settlement API client"""
    
    def __init__(self, transport: Transport):
        self.transport = transport
    
    async def settle_cross_chain(
        self,
        job_id: str,
        target_chain_id: int,
        bridge_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Initiate cross-chain settlement"""
        data = {
            'job_id': job_id,
            'target_chain_id': target_chain_id,
            'bridge_name': bridge_name
        }
        return await self.transport.request('POST', '/v1/settlement/cross-chain', data=data)
    
    async def get_settlement_status(self, message_id: str) -> Dict[str, Any]:
        """Get settlement status"""
        return await self.transport.request('GET', f'/v1/settlement/{message_id}/status')
    
    async def estimate_cost(
        self,
        job_id: str,
        target_chain_id: int,
        bridge_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Estimate settlement cost"""
        data = {
            'job_id': job_id,
            'target_chain_id': target_chain_id,
            'bridge_name': bridge_name
        }
        return await self.transport.request('POST', '/v1/settlement/estimate-cost', data=data)
    
    async def list_bridges(self) -> Dict[str, Any]:
        """List supported bridges"""
        return await self.transport.request('GET', '/v1/settlement/bridges')
    
    async def list_chains(self) -> Dict[str, Any]:
        """List supported chains"""
        return await self.transport.request('GET', '/v1/settlement/chains')
    
    async def refund_settlement(self, message_id: str) -> Dict[str, Any]:
        """Refund failed settlement"""
        return await self.transport.request('POST', f'/v1/settlement/{message_id}/refund')


class MultiNetworkSettlementAPI(SettlementAPI):
    """Multi-network Settlement API client"""
    
    def __init__(self, client: MultiNetworkClient):
        self.client = client
    
    async def settle_cross_chain(
        self,
        job_id: str,
        target_chain_id: int,
        source_chain_id: Optional[int] = None,
        bridge_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Initiate cross-chain settlement from specific network"""
        transport = self.client.get_transport(source_chain_id)
        data = {
            'job_id': job_id,
            'target_chain_id': target_chain_id,
            'bridge_name': bridge_name
        }
        return await transport.request('POST', '/v1/settlement/cross-chain', data=data)
    
    async def batch_settle(
        self,
        job_ids: List[str],
        target_chain_id: int,
        bridge_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Batch settle multiple jobs"""
        data = {
            'job_ids': job_ids,
            'target_chain_id': target_chain_id,
            'bridge_name': bridge_name
        }
        transport = self.client.get_transport()
        return await transport.request('POST', '/v1/settlement/batch', data=data)
