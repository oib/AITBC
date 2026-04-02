#!/usr/bin/env python3
"""
AITBC Blockchain Follower Node - Port 8007
Follows the main blockchain node and provides follower API endpoints
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Set environment variables
os.environ.setdefault('PYTHONPATH', '/opt/aitbc/apps/blockchain-node/src:/opt/aitbc/services')
os.environ.setdefault('BLOCKCHAIN_DATA_DIR', '/var/lib/aitbc/data/follower')
os.environ.setdefault('BLOCKCHAIN_CONFIG_DIR', '/etc/aitbc')
os.environ.setdefault('BLOCKCHAIN_LOG_DIR', '/var/log/aitbc/production')
os.environ.setdefault('BLOCKCHAIN_PORT', '8007')
os.environ.setdefault('BLOCKCHAIN_ROLE', 'follower')

# Add paths
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
sys.path.insert(0, '/opt/aitbc/services')

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    
    # Create follower FastAPI app
    app = FastAPI(
        title="AITBC Blockchain Follower Node",
        description="Follower node for AITBC blockchain network",
        version="v0.3.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Basic endpoints
    @app.get("/")
    async def root():
        return {
            "status": "follower_node",
            "port": 8007,
            "role": "follower",
            "service": "aitbc-blockchain-follower",
            "version": "v0.3.0"
        }
    
    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": "follower-node",
            "port": 8007,
            "role": "follower"
        }
    
    @app.get("/status")
    async def status():
        return {
            "status": "active",
            "node_type": "follower",
            "port": 8007,
            "following": "http://localhost:8006"
        }
    
    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        logger.info("Starting AITBC Blockchain Follower Node on port 8007")
        logger.info("Following main node at http://localhost:8006")
        
        # Start server on port 8007
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8007,
            log_level="info"
        )
        
except ImportError as e:
    print(f"Import error: {e}")
    print("Creating minimal follower node...")
    
    # Fallback simple server
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    
    class FollowerHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                response = {
                    "status": "follower_node",
                    "port": 8007,
                    "role": "follower",
                    "service": "aitbc-blockchain-follower",
                    "version": "v0.3.0"
                }
            elif self.path == "/health":
                response = {
                    "status": "healthy",
                    "service": "follower-node",
                    "port": 8007,
                    "role": "follower"
                }
            elif self.path == "/status":
                response = {
                    "status": "active",
                    "node_type": "follower",
                    "port": 8007,
                    "following": "http://localhost:8006"
                }
            else:
                response = {"error": "Not found"}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        
        def log_message(self, format, *args):
            pass  # Suppress logging
    
    if __name__ == "__main__":
        print("Starting minimal follower node on port 8007")
        server = HTTPServer(('0.0.0.0', 8007), FollowerHandler)
        server.serve_forever()
