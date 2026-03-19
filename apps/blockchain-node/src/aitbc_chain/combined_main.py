#!/usr/bin/env python3
"""
Combined blockchain node and P2P service launcher
Runs both the main blockchain node and P2P placeholder service
"""

import asyncio
import logging
import os
import signal
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
        self._stop_event = asyncio.Event()
        self._tasks = []
        self._loop = None
        
    def set_stop_event(self):
        """Set the stop event to trigger shutdown"""
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()
        
    async def start(self):
        """Start both blockchain node and P2P server"""
        self._loop = asyncio.get_running_loop()
        logger.info("Starting combined blockchain service")
        
        # Start blockchain node in background
        node_task = asyncio.create_task(run_node())
        self._tasks.append(node_task)
        
        logger.info(f"Combined service started - Node on mainnet")
        
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop all services"""
        logger.info("Stopping combined blockchain service")
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("Combined service stopped")

# Global service instance for signal handler
_service_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating shutdown")
    global _service_instance
    if _service_instance:
        _service_instance.set_stop_event()

async def main():
    """Main entry point"""
    global _service_instance
    service = CombinedService()
    _service_instance = service
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await service.stop()
        _service_instance = None

if __name__ == "__main__":
    asyncio.run(main())
