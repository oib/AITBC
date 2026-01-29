"""
Cross-site RPC synchronization module for AITBC blockchain nodes.
Enables block and transaction synchronization across different sites via HTTP RPC endpoints.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CrossSiteSync:
    """Handles synchronization with remote blockchain nodes via RPC."""
    
    def __init__(self, local_rpc_url: str, remote_endpoints: List[str], poll_interval: int = 10):
        """
        Initialize cross-site synchronization.
        
        Args:
            local_rpc_url: URL of local RPC endpoint (e.g., "http://localhost:8082")
            remote_endpoints: List of remote RPC URLs to sync with
            poll_interval: Seconds between sync checks
        """
        self.local_rpc_url = local_rpc_url.rstrip('/')
        self.remote_endpoints = remote_endpoints
        self.poll_interval = poll_interval
        self.last_sync = {}
        self.sync_task = None
        self.client = httpx.AsyncClient(timeout=5.0)
        
    async def get_remote_head(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Get the head block from a remote node."""
        try:
            response = await self.client.get(f"{endpoint.rstrip('/')}/head")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get head from {endpoint}: {e}")
        return None
        
    async def get_remote_block(self, endpoint: str, height: int) -> Optional[Dict[str, Any]]:
        """Get a specific block from a remote node."""
        try:
            response = await self.client.get(f"{endpoint.rstrip('/')}/blocks/{height}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get block {height} from {endpoint}: {e}")
        return None
        
    async def get_local_head(self) -> Optional[Dict[str, Any]]:
        """Get the local head block."""
        try:
            response = await self.client.get(f"{self.local_rpc_url}/rpc/head")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get local head: {e}")
        return None
        
    async def import_block(self, block_data: Dict[str, Any]) -> bool:
        """Import a block from a remote node."""
        try:
            response = await self.client.post(
                f"{self.local_rpc_url}/rpc/blocks/import",
                json=block_data
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("status") in ["imported", "exists"]:
                    logger.info(f"Successfully imported block {block_data.get('height')}")
                    return True
                else:
                    logger.error(f"Block import failed: {result}")
                    return False
            else:
                logger.error(f"Block import request failed: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to import block: {e}")
            return False
            
    async def submit_block(self, block_data: Dict[str, Any]) -> bool:
        """Submit a block to the local node."""
        try:
            response = await self.client.post(
                f"{self.local_rpc_url}/rpc/block",
                json=block_data
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to submit block: {e}")
            return False
            
    async def sync_with_remotes(self) -> None:
        """Check and sync with all remote endpoints."""
        local_head = await self.get_local_head()
        if not local_head:
            return
            
        local_height = local_head.get('height', 0)
        
        for endpoint in self.remote_endpoints:
            remote_head = await self.get_remote_head(endpoint)
            if not remote_head:
                continue
                
            remote_height = remote_head.get('height', 0)
            
            # If remote is ahead, fetch missing blocks
            if remote_height > local_height:
                logger.info(f"Remote {endpoint} is ahead (height {remote_height} vs {local_height})")
                
                # Fetch missing blocks one by one
                for height in range(local_height + 1, remote_height + 1):
                    block = await self.get_remote_block(endpoint, height)
                    if block:
                        # Format block data for import
                        import_data = {
                            "height": block.get("height"),
                            "hash": block.get("hash"),
                            "parent_hash": block.get("parent_hash"),
                            "proposer": block.get("proposer"),
                            "timestamp": block.get("timestamp"),
                            "tx_count": block.get("tx_count", 0),
                            "state_root": block.get("state_root"),
                            "transactions": block.get("transactions", []),
                            "receipts": block.get("receipts", [])
                        }
                        success = await self.import_block(import_data)
                        if success:
                            logger.info(f"Imported block {height} from {endpoint}")
                            local_height = height
                        else:
                            logger.error(f"Failed to import block {height}")
                            break
                    else:
                        logger.error(f"Failed to fetch block {height} from {endpoint}")
                        break
                        
    async def get_remote_mempool(self, endpoint: str) -> List[Dict[str, Any]]:
        """Get mempool transactions from a remote node."""
        try:
            response = await self.client.get(f"{endpoint.rstrip('/')}/mempool")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get mempool from {endpoint}: {e}")
        return []
        
    async def get_local_mempool(self) -> List[Dict[str, Any]]:
        """Get local mempool transactions."""
        try:
            response = await self.client.get(f"{self.local_rpc_url}/rpc/mempool")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get local mempool: {e}")
        return []
        
    async def submit_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """Submit a transaction to the local node."""
        try:
            response = await self.client.post(
                f"{self.local_rpc_url}/rpc/transaction",
                json=tx_data
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to submit transaction: {e}")
            return False
            
    async def sync_transactions(self) -> None:
        """Sync transactions from remote mempools."""
        local_mempool = await self.get_local_mempool()
        local_tx_hashes = {tx.get('hash') for tx in local_mempool}
        
        for endpoint in self.remote_endpoints:
            remote_mempool = await self.get_remote_mempool(endpoint)
            for tx in remote_mempool:
                tx_hash = tx.get('hash')
                if tx_hash and tx_hash not in local_tx_hashes:
                    success = await self.submit_transaction(tx)
                    if success:
                        logger.info(f"Imported transaction {tx_hash[:8]}... from {endpoint}")
                        
    async def sync_loop(self) -> None:
        """Main synchronization loop."""
        logger.info("Starting cross-site sync loop")
        
        while True:
            try:
                # Sync blocks
                await self.sync_with_remotes()
                
                # Sync transactions
                await self.sync_transactions()
                
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                
            await asyncio.sleep(self.poll_interval)
            
    async def start(self) -> None:
        """Start the synchronization task."""
        if self.sync_task is None:
            self.sync_task = asyncio.create_task(self.sync_loop())
            
    async def stop(self) -> None:
        """Stop the synchronization task."""
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
            self.sync_task = None
            
        await self.client.aclose()
