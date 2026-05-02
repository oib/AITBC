#!/usr/bin/env python3
"""
Chain Synchronization Service
Keeps blockchain nodes synchronized by sharing blocks via P2P and Redis gossip
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List

from aitbc import get_logger

logger = get_logger(__name__)

# Import settings for configuration
try:
    from .config import settings
except ImportError:
    # Fallback if settings not available
    class Settings:
        blockchain_monitoring_interval_seconds = 10
    settings = Settings()

class ChainSyncService:
    def __init__(self, redis_url: str, node_id: str, rpc_port: int = 8006, leader_host: str = None,
                 source_host: str = "127.0.0.1", source_port: int = None,
                 import_host: str = "127.0.0.1", import_port: int = None,
                 chain_id: str = ""):
        self.redis_url = redis_url
        self.node_id = node_id
        self.rpc_port = rpc_port  # kept for backward compat (local poll if source_port None)
        self.leader_host = leader_host  # Host of the leader node (legacy)
        self.source_host = source_host
        self.source_port = source_port or rpc_port
        self.import_host = import_host
        self.import_port = import_port or rpc_port
        self.chain_id = chain_id or getattr(settings, 'chain_id', '') or "ait-mainnet"
        self._stop_event = asyncio.Event()
        self._redis = None
        self._receiver_ready = asyncio.Event()
        
    async def start(self):
        """Start chain synchronization service"""
        logger.info(f"Starting chain sync service for node {self.node_id}")
        
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            logger.info("Connected to Redis for chain sync")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return
        
        # Start block broadcasting task
        # Start block receiving task
        receive_task = asyncio.create_task(self._receive_blocks())
        # Wait until receiver subscribed so we don't drop the initial burst
        await self._receiver_ready.wait()
        broadcast_task = asyncio.create_task(self._broadcast_blocks())
        
        try:
            await self._stop_event.wait()
        finally:
            broadcast_task.cancel()
            receive_task.cancel()
            await asyncio.gather(broadcast_task, receive_task, return_exceptions=True)
            
        if self._redis:
            await self._redis.close()
    
    async def stop(self):
        """Stop chain synchronization service"""
        logger.info("Stopping chain sync service")
        self._stop_event.set()

    async def _get_import_head_height(self, session) -> int:
        """Get the current height on the local import target."""
        try:
            async with session.get(
                f"http://{self.import_host}:{self.import_port}/rpc/head",
                params={"chain_id": self.chain_id},
            ) as resp:
                if resp.status == 200:
                    head_data = await resp.json()
                    return int(head_data.get('height', 0))
                if resp.status == 404:
                    return -1
                logger.warning(f"Failed to get import head height: RPC returned status {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to get import head height: {e}")
        return -1
    
    async def _broadcast_blocks(self):
        """Broadcast local blocks to other nodes"""
        import aiohttp
        
        last_broadcast_height = -1
        retry_count = 0
        max_retries = 5
        base_delay = settings.blockchain_monitoring_interval_seconds  # Use config setting instead of hardcoded value
        
        while not self._stop_event.is_set():
            try:
                # Get current head from local RPC
                async with aiohttp.ClientSession() as session:
                    if last_broadcast_height < 0:
                        last_broadcast_height = await self._get_import_head_height(session)
                        logger.info(f"Initialized sync baseline at height {last_broadcast_height} for node {self.node_id}")

                    async with session.get(f"http://{self.source_host}:{self.source_port}/rpc/head", params={"chain_id": self.chain_id}) as resp:
                        if resp.status == 200:
                            head_data = await resp.json()
                            current_height = head_data.get('height', 0)
                            
                            # Reset retry count on successful connection
                            retry_count = 0
                            
                            # Broadcast new blocks
                            if current_height > last_broadcast_height:
                                for height in range(last_broadcast_height + 1, current_height + 1):
                                    block_data = await self._get_block_by_height(height, session)
                                    if block_data:
                                        await self._broadcast_block(block_data)
                                
                                last_broadcast_height = current_height
                                logger.info(f"Broadcasted blocks up to height {current_height}")
                        elif resp.status == 429:
                            raise Exception("rate_limit")
                        else:
                            raise Exception(f"RPC returned status {resp.status}")
                
            except Exception as e:
                retry_count += 1
                # If rate-limited, wait longer before retrying
                if str(e) == "rate_limit":
                    delay = base_delay * 30
                    logger.warning(f"RPC rate limited, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                if retry_count <= max_retries:
                    delay = base_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    logger.warning(f"RPC connection failed (attempt {retry_count}/{max_retries}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"RPC connection failed after {max_retries} attempts, waiting {base_delay * 10}s: {e}")
                    await asyncio.sleep(base_delay * 10)
                    retry_count = 0  # Reset retry count after long wait
            
            await asyncio.sleep(base_delay)  # Check every 2 seconds when connected
    
    async def _receive_blocks(self):
        """Receive blocks from other nodes via Redis"""
        if not self._redis:
            return
            
        pubsub = self._redis.pubsub()
        channel = f"blocks.{self.chain_id}" if self.chain_id else "blocks"
        await pubsub.subscribe(channel)
        self._receiver_ready.set()
        
        logger.info(f"Subscribed to block broadcasts on channel: {channel}")
        
        async for message in pubsub.listen():
            if self._stop_event.is_set():
                break
                
            if message['type'] == 'message':
                try:
                    block_data = json.loads(message['data'])
                    await self._import_block(block_data)
                except Exception as e:
                    logger.error(f"Error processing received block: {e}")
    
    async def _get_block_by_height(self, height: int, session) -> Optional[Dict[str, Any]]:
        """Get block data by height from local RPC"""
        try:
            async with session.get(f"http://{self.source_host}:{self.source_port}/rpc/blocks-range?start={height}&end={height}") as resp:
                if resp.status == 200:
                    blocks_data = await resp.json()
                    blocks = blocks_data.get('blocks', [])
                    block = blocks[0] if blocks else None
                    return block
        except Exception as e:
            logger.error(f"Error getting block {height}: {e}")
        return None
    
    async def _broadcast_block(self, block_data: Dict[str, Any]):
        """Broadcast block to other nodes via Redis"""
        if not self._redis:
            return
            
        try:
            await self._redis.publish("blocks", json.dumps(block_data))
            logger.info(f"Broadcasted block {block_data.get('height')}")
        except Exception as e:
            logger.error(f"Error broadcasting block: {e}")
    
    async def _import_block(self, block_data: Dict[str, Any]):
        """Import block from another node"""
        import aiohttp
        
        try:
            # Don't import our own blocks
            if block_data.get('proposer') == self.node_id:
                return
            
            # Determine target host - if we're a follower, import to leader, else import locally
            target_host = self.import_host
            target_port = self.import_port
            
            # Retry logic for import
            max_retries = 3
            base_delay = 1
            
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"http://{target_host}:{target_port}/rpc/importBlock",
                            json=block_data
                        ) as resp:
                            if resp.status == 200:
                                result = await resp.json()
                                if result.get('accepted'):
                                    logger.info(f"Imported block {block_data.get('height')} from {block_data.get('proposer')}")
                                else:
                                    logger.info(f"Rejected block {block_data.get('height')}: {result.get('reason')}")
                                return
                            else:
                                try:
                                    body = await resp.text()
                                except Exception:
                                    body = "<no body>"
                                raise Exception(f"HTTP {resp.status}: {body}")
                
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Import failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Failed to import block {block_data.get('height')} after {max_retries} attempts: {e}")
                        return
                        
        except Exception as e:
            logger.error(f"Error importing block: {e}")

async def run_chain_sync(
    redis_url: str,
    node_id: str,
    rpc_port: int = 8006,
    leader_host: str = None,
    source_host: str = "127.0.0.1",
    source_port: int = None,
    import_host: str = "127.0.0.1",
    import_port: int = None,
    chain_id: str = "",
):
    """Run chain synchronization service"""
    service = ChainSyncService(
        redis_url=redis_url,
        node_id=node_id,
        rpc_port=rpc_port,
        leader_host=leader_host,
        source_host=source_host,
        source_port=source_port,
        import_host=import_host,
        import_port=import_port,
        chain_id=chain_id,
    )
    await service.start()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC Chain Synchronization Service")
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--node-id", required=True, help="Node identifier")
    parser.add_argument("--rpc-port", type=int, default=8006, help="RPC port")
    parser.add_argument("--leader-host", help="Leader node host (for followers)")
    parser.add_argument("--source-host", default="127.0.0.1", help="Host to poll for head/blocks")
    parser.add_argument("--source-port", type=int, help="Port to poll for head/blocks")
    parser.add_argument("--import-host", default="127.0.0.1", help="Host to import blocks into")
    parser.add_argument("--import-port", type=int, help="Port to import blocks into")
    parser.add_argument("--chain-id", default="", help="Chain ID to sync (e.g., ait-testnet)")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        asyncio.run(run_chain_sync(
            args.redis,
            args.node_id,
            args.rpc_port,
            args.leader_host,
            args.source_host,
            args.source_port,
            args.import_host,
            args.import_port,
            args.chain_id,
        ))
    except KeyboardInterrupt:
        logger.info("Chain sync service stopped by user")

if __name__ == "__main__":
    main()
