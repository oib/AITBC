"""
Simple gossip relay service for blockchain nodes
Uses Starlette Broadcast to share messages between nodes
"""
import argparse
import logging
import uvicorn
from typing import Any
from aitbc.logging import get_logger  # type: ignore[import-not-found]
from starlette.applications import Starlette
from starlette.broadcast import Broadcast  # type: ignore[import-not-found]
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
logging.basicConfig(level=logging.INFO)
logger = get_logger(__name__)
broadcast = Broadcast('memory://')

async def gossip_endpoint(request: Any) -> dict[str, str]:
    """HTTP endpoint for publishing gossip messages"""
    try:
        data = await request.json()
        channel = data.get('channel', 'blockchain')
        message = data.get('message')
        if message:
            await broadcast.publish(channel, message)
            logger.info('Published to %s: %s...', channel, str(message)[:50])
            return {'status': 'published', 'channel': channel}
        else:
            return {'status': 'error', 'message': 'No message provided'}
    except Exception as e:
        logger.error('Error publishing: %s', e)
        return {'status': 'error', 'message': str(e)}

async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time gossip"""
    await websocket.accept()
    channel = websocket.query_params.get('channel', 'blockchain')
    logger.info('WebSocket connected to channel: %s', channel)
    try:
        async with broadcast.subscribe(channel) as subscriber:
            async for message in subscriber:
                await websocket.send_text(message)
    except Exception as e:
        logger.error('WebSocket error: %s', e)
    finally:
        logger.info('WebSocket disconnected')

def create_app() -> Starlette:
    """Create the Starlette application"""
    routes = [Route('/gossip', gossip_endpoint, methods=['POST']), WebSocketRoute('/ws', websocket_endpoint)]
    middleware = [Middleware(CORSMiddleware, allow_origins=['http://localhost:8011', 'http://localhost:8001', 'http://localhost:8002', 'http://localhost:8003', 'http://localhost:8010', 'http://localhost:8011', 'http://localhost:8012', 'http://localhost:8013', 'http://localhost:8014', 'http://localhost:8015', 'http://localhost:8016'], allow_methods=['POST', 'GET', 'OPTIONS'])]
    return Starlette(routes=routes, middleware=middleware)

def main() -> None:
    parser = argparse.ArgumentParser(description='AITBC Gossip Relay')
    parser.add_argument('--host', default='127.0.0.1', help='Bind host')
    parser.add_argument('--port', type=int, default=7070, help='Bind port')
    parser.add_argument('--log-level', default='info', help='Log level')
    args = parser.parse_args()
    logger.info('Starting gossip relay on %s:%s', args.host, args.port)
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
if __name__ == '__main__':
    main()