"""
Jobs API for AITBC Python SDK
"""

from typing import Dict, Any, Optional, List
import logging

from ..transport import Transport
from ..transport.multinetwork import MultiNetworkClient

logger = logging.getLogger(__name__)


class JobsAPI:
    """Jobs API client"""
    
    def __init__(self, transport: Transport):
        self.transport = transport
    
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new job"""
        return await self.transport.request('POST', '/v1/jobs', data=data)
    
    async def get(self, job_id: str) -> Dict[str, Any]:
        """Get job details"""
        return await self.transport.request('GET', f'/v1/jobs/{job_id}')
    
    async def list(self, **params) -> List[Dict[str, Any]]:
        """List jobs"""
        response = await self.transport.request('GET', '/v1/jobs', params=params)
        return response.get('jobs', [])
    
    async def update(self, job_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update job"""
        return await self.transport.request('PUT', f'/v1/jobs/{job_id}', data=data)
    
    async def delete(self, job_id: str) -> None:
        """Delete job"""
        await self.transport.request('DELETE', f'/v1/jobs/{job_id}')
    
    async def wait_for_completion(
        self, 
        job_id: str, 
        timeout: Optional[int] = None,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Wait for job completion"""
        # Implementation would poll job status until complete
        pass


class MultiNetworkJobsAPI(JobsAPI):
    """Multi-network Jobs API client"""
    
    def __init__(self, client: MultiNetworkClient):
        self.client = client
    
    async def create(
        self, 
        data: Dict[str, Any], 
        chain_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new job on specific network"""
        transport = self.client.get_transport(chain_id)
        return await transport.request('POST', '/v1/jobs', data=data)
    
    async def get(
        self, 
        job_id: str, 
        chain_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get job details from specific network"""
        transport = self.client.get_transport(chain_id)
        return await transport.request('GET', f'/v1/jobs/{job_id}')
    
    async def list(
        self, 
        chain_id: Optional[int] = None,
        **params
    ) -> List[Dict[str, Any]]:
        """List jobs from specific network"""
        transport = self.client.get_transport(chain_id)
        response = await transport.request('GET', '/v1/jobs', params=params)
        return response.get('jobs', [])
    
    async def broadcast_create(
        self, 
        data: Dict[str, Any],
        chain_ids: Optional[List[int]] = None
    ) -> Dict[int, Dict[str, Any]]:
        """Create job on multiple networks"""
        return await self.client.broadcast_request(
            'POST', '/v1/jobs', data=data, chain_ids=chain_ids
        )
