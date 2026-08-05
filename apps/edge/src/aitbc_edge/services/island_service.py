"""Island service for Edge API Service"""

import os
import socket
from typing import Any

from aitbc.aitbc_logging import get_logger

from sqlmodel import select

from ..clients.blockchain_rpc import BlockchainRPCClient
from ..schemas.island import BridgeRequest, IslandMembership, IslandStatus
from ..storage import get_session

logger = get_logger(__name__)

# Node identity for bridge request attribution.
# Same derivation as main._register_edge_node_on_blockchain so the node has
# one consistent identity across all code paths.
NODE_ID = os.getenv("EDGE_NODE_ID", os.getenv("NODE_ID", f"edge-{socket.gethostname()}"))


class IslandService:
    """Service for island operations"""

    async def join_island(
        self,
        island_id: str,
        island_name: str,
        chain_id: str | list[str],
        role: str = "compute-provider",
        is_hub: bool = False,
        region: str | None = None,
    ) -> dict[str, Any]:
        """Join an island via blockchain RPC"""
        # Call blockchain RPC to join island
        async with BlockchainRPCClient() as rpc_client:
            result = await rpc_client.join_island(island_id, island_name, chain_id, role, is_hub)

        # Store membership in edge-api database
        if result.get("success"):
            async with get_session() as session:
                # Map blockchain status string to IslandStatus enum
                # PostgreSQL enum only has: active, inactive, bridging
                # Map "joined" to "active"
                raw_status = result.get("status", "active").lower()
                if raw_status == "joined":
                    raw_status = "active"
                try:
                    status = IslandStatus(raw_status)
                except ValueError:
                    status = IslandStatus.ACTIVE
                extra_data: dict[str, Any] = {}
                if region:
                    extra_data["region"] = region
                if is_hub:
                    extra_data["is_hub"] = is_hub
                membership = IslandMembership(
                    island_id=island_id,
                    island_name=island_name,
                    chain_id=chain_id,
                    role=role,
                    status=status,
                    extra_data=extra_data,
                )
                session.add(membership)
                await session.commit()

        return result

    async def leave_island(self, island_id: str) -> dict[str, Any]:
        """Leave an island via blockchain RPC"""
        # Call blockchain RPC to leave island
        async with BlockchainRPCClient() as rpc_client:
            result = await rpc_client.leave_island(island_id)

        # Remove membership from edge-api database
        if result.get("success"):
            async with get_session() as session:
                from sqlmodel import delete

                stmt = delete(IslandMembership).where(IslandMembership.island_id == island_id)  # type: ignore[arg-type]
                await session.execute(stmt)
                await session.commit()

        return result

    async def list_islands(self) -> list[dict[str, Any]]:
        """List all islands via blockchain RPC"""
        async with BlockchainRPCClient() as rpc_client:
            result = await rpc_client.list_islands()
        islands = result.get("islands", [])
        return islands if isinstance(islands, list) else []

    async def get_island(self, island_id: str) -> dict[str, Any] | None:
        """Get island details via blockchain RPC"""
        async with BlockchainRPCClient() as rpc_client:
            result = await rpc_client.get_island_info(island_id)
        return result

    async def list_memberships_by_region(self, region: str) -> list[IslandMembership]:
        """List edge node island memberships for a given region."""
        async with get_session() as session:
            stmt = select(IslandMembership)
            result = await session.execute(stmt)
            memberships = result.scalars().all()
            return [m for m in memberships if m.extra_data.get("region") == region]

    async def request_bridge(self, target_island_id: str) -> dict[str, Any]:
        """Request bridge to another island via blockchain RPC"""
        async with BlockchainRPCClient() as rpc_client:
            result = await rpc_client.request_bridge(target_island_id)

        # Store bridge request in edge-api database
        if result.get("success"):
            async with get_session() as session:
                bridge_req = BridgeRequest(
                    request_id=result.get("request_id"),
                    target_island_id=target_island_id,
                    source_node_id=NODE_ID,
                    status=result.get("status", "pending"),
                )
                session.add(bridge_req)
                await session.commit()

        return result
