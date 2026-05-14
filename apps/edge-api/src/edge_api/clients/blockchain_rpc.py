"""Blockchain RPC client for Edge API Service"""

import httpx
from typing import Dict, Optional

from ..config import settings


class BlockchainRPCClient:
    """Client for blockchain node RPC communication"""
    
    def __init__(self):
        self.base_url = f"http://{settings.blockchain_rpc_host}:{settings.blockchain_rpc_port}"
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def join_island(self, island_id: str, island_name: str, chain_id: str, role: str) -> Dict:
        """Join island via blockchain RPC - TODO: Implement in Phase 2"""
        # TODO: Call blockchain node RPC endpoint for island join
        return {"message": "join_island via RPC - to be implemented in Phase 2"}
    
    async def leave_island(self, island_id: str) -> Dict:
        """Leave island via blockchain RPC - TODO: Implement in Phase 2"""
        # TODO: Call blockchain node RPC endpoint for island leave
        return {"message": "leave_island via RPC - to be implemented in Phase 2"}
    
    async def get_island_info(self, island_id: str) -> Optional[Dict]:
        """Get island info via blockchain RPC - TODO: Implement in Phase 2"""
        # TODO: Call blockchain node RPC endpoint for island info
        return {"message": "get_island_info via RPC - to be implemented in Phase 2"}
    
    async def request_bridge(self, target_island_id: str) -> Dict:
        """Request bridge via blockchain RPC - TODO: Implement in Phase 2"""
        # TODO: Call blockchain node RPC endpoint for bridge request
        return {"message": "request_bridge via RPC - to be implemented in Phase 2"}
