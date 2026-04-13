#!/usr/bin/env python3
"""
Combined blockchain node and P2P service launcher
Runs both the main blockchain node and P2P placeholder service
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aitbc_chain.main import BlockchainNode, _run as run_node
from aitbc_chain.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CombinedService:
    def __init__(self):
        self._tasks = []
        
    async def start(self):
        """Start both blockchain node and P2P server"""
        logger.info("Starting combined blockchain service")
        
        # Start blockchain node in background
        node_task = asyncio.create_task(run_node())
        self._tasks.append(node_task)
        
        logger.info(f"Combined service started - Node on mainnet")
        
        try:
            # Wait for the node task to complete
            await node_task
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop all services"""
        logger.info("Stopping combined blockchain service")
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("Combined service stopped")

async def main():
    """Main entry point"""
    service = CombinedService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())
