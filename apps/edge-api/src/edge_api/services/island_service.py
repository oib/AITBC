"""Island service for Edge API Service"""

from typing import Dict, List, Optional

from ..clients.blockchain_rpc import BlockchainRPCClient
from ..storage import get_session
from ..schemas.island import IslandMembership, BridgeRequest


class IslandService:
    """Service for island operations"""
    
    def __init__(self):
        self.rpc_client = BlockchainRPCClient()
    
    async def join_island(self, island_id: str, island_name: str, chain_id: str, role: str = "compute-provider", is_hub: bool = False) -> Dict:
        """Join an island via blockchain RPC"""
        # Call blockchain RPC to join island
        result = await self.rpc_client.join_island(island_id, island_name, chain_id, role, is_hub)
        
        # Store membership in edge-api database
        if result.get("success"):
            async with get_session() as session:
                membership = IslandMembership(
                    island_id=island_id,
                    island_name=island_name,
                    chain_id=chain_id,
                    role=role,
                    status=result.get("status", "active")
                )
                session.add(membership)
                await session.commit()
        
        return result
    
    async def leave_island(self, island_id: str) -> Dict:
        """Leave an island via blockchain RPC"""
        # Call blockchain RPC to leave island
        result = await self.rpc_client.leave_island(island_id)
        
        # Remove membership from edge-api database
        if result.get("success"):
            async with get_session() as session:
                from sqlmodel import delete
                stmt = delete(IslandMembership).where(IslandMembership.island_id == island_id)
                await session.execute(stmt)
                await session.commit()
        
        return result
    
    async def list_islands(self) -> List[Dict]:
        """List all islands via blockchain RPC"""
        result = await self.rpc_client.list_islands()
        return result.get("islands", [])
    
    async def get_island(self, island_id: str) -> Optional[Dict]:
        """Get island details via blockchain RPC"""
        result = await self.rpc_client.get_island_info(island_id)
        return result
    
    async def request_bridge(self, target_island_id: str) -> Dict:
        """Request bridge to another island via blockchain RPC"""
        result = await self.rpc_client.request_bridge(target_island_id)
        
        # Store bridge request in edge-api database
        if result.get("success"):
            async with get_session() as session:
                bridge_req = BridgeRequest(
                    request_id=result.get("request_id"),
                    target_island_id=target_island_id,
                    source_node_id="edge-api",  # TODO: Get actual node ID
                    status=result.get("status", "pending")
                )
                session.add(bridge_req)
                await session.commit()
        
        return result
