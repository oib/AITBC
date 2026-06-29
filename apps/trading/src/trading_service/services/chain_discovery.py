"""Chain discovery service for inter-chain trading (v0.8.0 §B4).

Manages the island registry: registering chains, syncing their health
status, and providing chain discovery for the matching engine.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..clients.blockchain import BlockchainClient
from ..config import settings
from ..domain.inter_chain import IslandRegistryEntry

logger = logging.getLogger(__name__)


class ChainDiscoveryService:
    """Service for managing the island registry and chain discovery."""

    def __init__(self, session: AsyncSession, blockchain_client: BlockchainClient | None = None) -> None:
        self.session = session
        self._blockchain = blockchain_client or BlockchainClient(
            rpc_url=settings.blockchain_rpc_url,
            timeout=settings.http_timeout,
        )

    async def register_chain(self, chain_id: str, endpoint: str) -> IslandRegistryEntry:
        """Register a new chain in the island registry.

        If the chain already exists, updates its endpoint and reactivates it.
        """
        stmt = select(IslandRegistryEntry).where(IslandRegistryEntry.chain_id == chain_id)
        result = await self.session.execute(stmt)
        entry = result.scalars().first()

        if entry:
            entry.endpoint = endpoint
            entry.status = "active"
            entry.last_sync = datetime.now(UTC)
        else:
            entry = IslandRegistryEntry(chain_id=chain_id, endpoint=endpoint, status="active")
            self.session.add(entry)

        await self.session.commit()
        await self.session.refresh(entry)
        logger.info("Registered chain %s at %s", chain_id, endpoint)
        return entry

    async def list_chains(self, status: str | None = None) -> list[IslandRegistryEntry]:
        """List all registered chains, optionally filtered by status."""
        stmt = select(IslandRegistryEntry)
        if status:
            stmt = stmt.where(IslandRegistryEntry.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_chain(self, chain_id: str) -> IslandRegistryEntry | None:
        """Get a specific chain from the registry."""
        stmt = select(IslandRegistryEntry).where(IslandRegistryEntry.chain_id == chain_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_chain_health(self, chain_id: str) -> dict[str, Any]:
        """Get health metrics for a specific chain.

        Queries the chain's blockchain node RPC for health info and
        updates the registry entry's block_height and last_sync.
        """
        entry = await self.get_chain(chain_id)
        if not entry:
            return {"chain_id": chain_id, "status": "not_registered"}

        try:
            # Query the chain's blockchain node for health
            client = BlockchainClient(rpc_url=entry.endpoint, timeout=settings.http_timeout)
            health = await client.get_chain_health(chain_id)
            block_height = await client.get_block_height(chain_id)

            # Update registry entry
            entry.block_height = block_height
            entry.status = "active"
            entry.last_sync = datetime.now(UTC)
            await self.session.commit()

            return {
                "chain_id": chain_id,
                "endpoint": entry.endpoint,
                "status": "active",
                "block_height": block_height,
                "health": health,
                "last_sync": entry.last_sync.isoformat(),
            }
        except Exception as e:
            logger.warning("Chain %s health check failed: %s", chain_id, e)
            entry.status = "unreachable"
            entry.last_sync = datetime.now(UTC)
            await self.session.commit()
            return {
                "chain_id": chain_id,
                "endpoint": entry.endpoint,
                "status": "unreachable",
                "error": str(e),
                "last_sync": entry.last_sync.isoformat(),
            }

    async def sync_island_registry(self) -> dict[str, Any]:
        """Sync all registered chains' health status.

        Polls each registered chain's blockchain node RPC and updates
        block_height + status. Called periodically by the sync loop.
        """
        chains = await self.list_chains()
        results: dict[str, Any] = {"synced": 0, "unreachable": 0, "total": len(chains)}

        for chain in chains:
            try:
                client = BlockchainClient(rpc_url=chain.endpoint, timeout=settings.http_timeout)
                block_height = await client.get_block_height(chain.chain_id)
                chain.block_height = block_height
                chain.status = "active"
                chain.last_sync = datetime.now(UTC)
                results["synced"] += 1
            except Exception as e:
                logger.warning("Failed to sync chain %s: %s", chain.chain_id, e)
                chain.status = "unreachable"
                chain.last_sync = datetime.now(UTC)
                results["unreachable"] += 1

        await self.session.commit()
        return results
