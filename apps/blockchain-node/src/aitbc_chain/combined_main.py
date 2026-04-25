#!/usr/bin/env python3
"""
Combined blockchain node and P2P service launcher
Runs both the main blockchain node, P2P placeholder service, and HTTP RPC server
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aitbc import get_logger
from aitbc_chain.main import BlockchainNode, _run as run_node
from aitbc_chain.config import settings
from aitbc_chain.app import create_app
import uvicorn

logger = get_logger(__name__)

class CombinedService:
    def __init__(self):
        self._tasks = []
        self._http_server = None
        
    async def start(self):
        """Start both blockchain node and HTTP RPC server"""
        logger.info("Starting combined blockchain service")
        
        # Start blockchain node in background
        node_task = asyncio.create_task(run_node())
        self._tasks.append(node_task)
        
        # Start HTTP RPC server in background
        app = create_app()
        config = uvicorn.Config(
            app,
            host="0.0.0.0",  # nosec B104 - binding to all interfaces is intentional for blockchain node
            port=8005,
            log_level="info"
        )
        self._http_server = uvicorn.Server(config)
        http_task = asyncio.create_task(self._http_server.serve())
        self._tasks.append(http_task)
        
        logger.info("Combined service started - Node on mainnet, RPC server on port 8005")
        
        try:
            # Wait for any task to complete (should not happen in normal operation)
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop all services"""
        logger.info("Stopping combined blockchain service")
        
        # Shutdown HTTP server if running
        if self._http_server:
            self._http_server.should_exit = True
        
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
