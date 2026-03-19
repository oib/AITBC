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

logger = logging.getLogger(__name__)

class ChainSyncService:
    def __init__(self, redis_url: str, node_id: str, rpc_port: int = 8006, leader_host: str = None):
        self.redis_url = redis_url
        self.node_id = node_id
        self.rpc_port = rpc_port
        self.leader_host = leader_host  # Host of the leader node
        self._stop_event = asyncio.Event()
        self._redis = None
        
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
        broadcast_task = asyncio.create_task(self._broadcast_blocks())
        
        # Start block receiving task
        receive_task = asyncio.create_task(self._receive_blocks())
        
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
    
    async def _broadcast_blocks(self):
        """Broadcast local blocks to other nodes"""
        import aiohttp
        
        last_broadcast_height = 0
        
        while not self._stop_event.is_set():
            try:
                # Get current head from local RPC
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://127.0.0.1:{self.rpc_port}/rpc/head") as resp:
                        if resp.status == 200:
                            head_data = await resp.json()
                            current_height = head_data.get('height', 0)
                            
                            # Broadcast new blocks
                            if current_height > last_broadcast_height:
                                for height in range(last_broadcast_height + 1, current_height + 1):
                                    block_data = await self._get_block_by_height(height, session)
                                    if block_data:
                                        await self._broadcast_block(block_data)
                                
                                last_broadcast_height = current_height
                                logger.info(f"Broadcasted blocks up to height {current_height}")
                
            except Exception as e:
                logger.error(f"Error in block broadcast: {e}")
            
            await asyncio.sleep(2)  # Check every 2 seconds
    
    async def _receive_blocks(self):
        """Receive blocks from other nodes via Redis"""
        if not self._redis:
            return
            
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("blocks")
        
        logger.info("Subscribed to block broadcasts")
        
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
            async with session.get(f"http://127.0.0.1:{self.rpc_port}/rpc/blocks?start={height}&end={height}") as resp:
                if resp.status == 200:
                    blocks_data = await resp.json()
                    blocks = blocks_data.get('blocks', [])
                    return blocks[0] if blocks else None
        except Exception as e:
            logger.error(f"Error getting block {height}: {e}")
        return None
    
    async def _broadcast_block(self, block_data: Dict[str, Any]):
        """Broadcast block to other nodes via Redis"""
        if not self._redis:
            return
            
        try:
            await self._redis.publish("blocks", json.dumps(block_data))
            logger.debug(f"Broadcasted block {block_data.get('height')}")
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
            target_host = self.leader_host if self.leader_host else "127.0.0.1"
            target_port = self.rpc_port
            
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
                            logger.debug(f"Rejected block {block_data.get('height')}: {result.get('reason')}")
                    else:
                        logger.warning(f"Failed to import block: {resp.status}")
                        
        except Exception as e:
            logger.error(f"Error importing block: {e}")

async def run_chain_sync(redis_url: str, node_id: str, rpc_port: int = 8006, leader_host: str = None):
    """Run chain synchronization service"""
    service = ChainSyncService(redis_url, node_id, rpc_port, leader_host)
    await service.start()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC Chain Synchronization Service")
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--node-id", required=True, help="Node identifier")
    parser.add_argument("--rpc-port", type=int, default=8006, help="RPC port")
    parser.add_argument("--leader-host", help="Leader node host (for followers)")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        asyncio.run(run_chain_sync(args.redis, args.node_id, args.rpc_port, args.leader_host))
    except KeyboardInterrupt:
        logger.info("Chain sync service stopped by user")

if __name__ == "__main__":
    main()
