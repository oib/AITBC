#!/usr/bin/env python3
"""
Simple gossip relay service for blockchain nodes
Uses Starlette Broadcast to share messages between nodes
"""

import argparse
import asyncio
import logging
from typing import Any, Dict

from starlette.applications import Starlette
from starlette.broadcast import Broadcast
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
import uvicorn

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global broadcast instance
broadcast = Broadcast("memory://")


async def gossip_endpoint(request):
    """HTTP endpoint for publishing gossip messages"""
    try:
        data = await request.json()
        channel = data.get("channel", "blockchain")
        message = data.get("message")
        
        if message:
            await broadcast.publish(channel, message)
            logger.info(f"Published to {channel}: {str(message)[:50]}...")
            
            return {"status": "published", "channel": channel}
        else:
            return {"status": "error", "message": "No message provided"}
    except Exception as e:
        logger.error(f"Error publishing: {e}")
        return {"status": "error", "message": str(e)}


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time gossip"""
    await websocket.accept()
    
    # Get channel from query params
    channel = websocket.query_params.get("channel", "blockchain")
    logger.info(f"WebSocket connected to channel: {channel}")
    
    try:
        async with broadcast.subscribe(channel) as subscriber:
            async for message in subscriber:
                await websocket.send_text(message)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info("WebSocket disconnected")


def create_app() -> Starlette:
    """Create the Starlette application"""
    routes = [
        Route("/gossip", gossip_endpoint, methods=["POST"]),
        WebSocketRoute("/ws", websocket_endpoint),
    ]
    
    middleware = [
        Middleware(
            CORSMiddleware, 
            allow_origins=[
                "http://localhost:3000",
                "http://localhost:8080",
                "http://localhost:8000",
                "http://localhost:8011"
            ], 
            allow_methods=["POST", "GET", "OPTIONS"]
        )
    ]
    
    return Starlette(routes=routes, middleware=middleware)


def main():
    parser = argparse.ArgumentParser(description="AITBC Gossip Relay")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=7070, help="Bind port")
    parser.add_argument("--log-level", default="info", help="Log level")
    
    args = parser.parse_args()
    
    logger.info(f"Starting gossip relay on {args.host}:{args.port}")
    
    app = create_app()
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level
    )


if __name__ == "__main__":
    main()
