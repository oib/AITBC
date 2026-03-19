#!/usr/bin/env python3
"""
P2P Network Service using Redis Gossip
Handles peer-to-peer communication between blockchain nodes
"""

import asyncio
import json
import logging
import socket
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class P2PNetworkService:
    def __init__(self, host: str, port: int, redis_url: str, node_id: str):
        self.host = host
        self.port = port
        self.redis_url = redis_url
        self.node_id = node_id
        self._server = None
        self._stop_event = asyncio.Event()
        
    async def start(self):
        """Start P2P network service"""
        logger.info(f"Starting P2P network service on {self.host}:{self.port}")
        
        # Create TCP server for P2P connections
        self._server = await asyncio.start_server(
            self._handle_connection, 
            self.host, 
            self.port
        )
        
        logger.info(f"P2P service listening on {self.host}:{self.port}")
        
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop P2P network service"""
        logger.info("Stopping P2P network service")
        if self._server:
            self._server.close()
            await self._server.wait_closed()
    
    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming P2P connections"""
        addr = writer.get_extra_info('peername')
        logger.info(f"P2P connection from {addr}")
        
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                
                try:
                    message = json.loads(data.decode())
                    logger.info(f"P2P received: {message}")
                    
                    # Handle different message types
                    if message.get('type') == 'ping':
                        response = {'type': 'pong', 'node_id': self.node_id}
                        writer.write(json.dumps(response).encode() + b'\n')
                        await writer.drain()
                    
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {addr}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"P2P connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f"P2P connection closed from {addr}")

async def run_p2p_service(host: str, port: int, redis_url: str, node_id: str):
    """Run P2P service"""
    service = P2PNetworkService(host, port, redis_url, node_id)
    await service.start()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC P2P Network Service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8005, help="Bind port")
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--node-id", help="Node identifier")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        asyncio.run(run_p2p_service(args.host, args.port, args.redis, args.node_id))
    except KeyboardInterrupt:
        logger.info("P2P service stopped by user")

if __name__ == "__main__":
    main()
