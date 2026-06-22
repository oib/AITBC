"""
Simple gossip relay service for blockchain nodes
Uses in-memory broadcasting to share messages between nodes
"""

import argparse
import asyncio
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from aitbc.aitbc_logging import configure_logging, get_logger

configure_logging(level="INFO", service_name="blockchain-p2p", to_file=True)
logger = get_logger(__name__)


class SimpleBroadcast:
    """Simple in-memory broadcast replacement for starlette.broadcast"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def publish(self, channel: str, message: str) -> None:
        """Publish a message to all subscribers of a channel"""
        if channel not in self._subscribers:
            return
        for queue in self._subscribers[channel]:
            await queue.put(message)

    async def subscribe(self, channel: str) -> Any:
        """Subscribe to a channel and return an async iterator"""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[channel].append(queue)

        class Subscriber:
            def __init__(self, q: asyncio.Queue, subs: dict[str, list[asyncio.Queue]], ch: str) -> None:
                self.queue = q
                self.subscribers = subs
                self.channel = ch

            async def __aenter__(self) -> "Subscriber":
                return self

            async def __aexit__(self, *args: Any) -> None:
                if self.queue in self.subscribers.get(self.channel, []):
                    self.subscribers[self.channel].remove(self.queue)

            def __aiter__(self) -> "Subscriber":
                return self

            async def __anext__(self) -> str:
                return await self.queue.get()

        return Subscriber(queue, self._subscribers, channel)


broadcast = SimpleBroadcast()


async def gossip_endpoint(request: Any) -> dict[str, str]:
    """HTTP endpoint for publishing gossip messages"""
    try:
        data = await request.json()
        channel = data.get("channel", "blockchain")
        message = data.get("message")
        if message:
            await broadcast.publish(channel, message)
            logger.info("Published to %s: %s...", channel, str(message)[:50])
            return {"status": "published", "channel": channel}
        else:
            return {"status": "error", "message": "No message provided"}
    except Exception as e:
        logger.error("Error publishing: %s", e)
        return {"status": "error", "message": str(e)}


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time gossip"""
    await websocket.accept()
    channel = websocket.query_params.get("channel", "blockchain")
    logger.info("WebSocket connected to channel: %s", channel)
    try:
        async with broadcast.subscribe(channel) as subscriber:
            async for message in subscriber:
                await websocket.send_text(message)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        logger.info("WebSocket disconnected")


def create_app() -> Starlette:
    """Create the Starlette application"""
    routes = [Route("/gossip", gossip_endpoint, methods=["POST"]), WebSocketRoute("/ws", websocket_endpoint)]
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:8011",
                "http://localhost:8001",
                "http://localhost:8002",
                "http://localhost:8003",
                "http://localhost:8010",
                "http://localhost:8011",
                "http://localhost:8012",
                "http://localhost:8013",
                "http://localhost:8014",
                "http://localhost:8015",
                "http://localhost:8016",
            ],
            allow_methods=["POST", "GET", "OPTIONS"],
        )
    ]
    return Starlette(routes=routes, middleware=middleware)


def main() -> None:
    parser = argparse.ArgumentParser(description="AITBC Gossip Relay")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=7070, help="Bind port")
    parser.add_argument("--log-level", default="info", help="Log level")
    parser.add_argument("--access-log", action="store_true", default=False, help="Enable access logging")
    args = parser.parse_args()
    logger.info("Starting gossip relay on %s:%s", args.host, args.port)
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level, access_log=args.access_log)


if __name__ == "__main__":
    main()
