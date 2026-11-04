"""
Simple gossip relay service for blockchain nodes
Uses in-memory broadcasting to share messages between nodes
"""

import argparse
import asyncio
import json
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from aitbc.aitbc_logging import configure_logging, get_logger

from .gossip_auth import (
    create_challenge,
    is_public_topic,
    is_restricted_topic,
    verify_challenge,
)

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
                return await self.queue.get()  # type: ignore[no-any-return]

        return Subscriber(queue, self._subscribers, channel)


broadcast = SimpleBroadcast()


async def gossip_challenge(request: Any) -> JSONResponse:
    """Issue a challenge for publishers of validator-restricted topics.

    Same pattern as the node's /rpc/gossip/ws (#1065): the client signs
    {challenge, address, timestamp} with its validator key and posts the
    signature with the message.
    """
    challenge, ts = create_challenge()
    return JSONResponse({"challenge": challenge, "timestamp": ts})


def _publisher_authenticated(data: Any) -> bool:
    """True when the body carries a valid validator challenge response."""
    try:
        return bool(
            verify_challenge(
                str(data.get("challenge", "")),
                str(data.get("address", "")),
                float(data.get("timestamp", 0)),
                str(data.get("signature", "")),
            )
        )
    except (TypeError, ValueError):
        return False


async def gossip_endpoint(request: Any) -> JSONResponse:
    """HTTP endpoint for publishing gossip messages"""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)
    channel = str(data.get("channel", "blockchain"))
    message = data.get("message")
    if not message:
        return JSONResponse({"status": "error", "message": "No message provided"}, status_code=400)
    # Publishing to validator-restricted topics (blocks.*, pbft.*,
    # consensus.*) needs the signed challenge; unknown channels are
    # rejected outright — the relay used to publish anything to
    # anyone (#1065).
    if is_restricted_topic(channel):
        if not _publisher_authenticated(data):
            return JSONResponse(
                {"status": "error", "message": "Validator auth required"},
                status_code=401,
            )
    elif not is_public_topic(channel):
        return JSONResponse({"status": "error", "message": "Unknown gossip channel"}, status_code=403)
    await broadcast.publish(channel, message)
    logger.info("Published to %s: %s...", channel, str(message)[:50])
    return JSONResponse({"status": "published", "channel": channel})


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time gossip"""
    channel = websocket.query_params.get("channel", "blockchain")
    # Restricted topics need the validator challenge on SUBSCRIBE too —
    # publish-side auth alone leaves the streams readable (#1065). The
    # caller fetches a challenge from GET /gossip/challenge and signs it.
    if is_restricted_topic(channel) and not _publisher_authenticated(websocket.query_params):
        await websocket.close(code=1008)
        logger.warning("Rejected unauthenticated restricted subscribe: %s", channel)
        return
    await websocket.accept()
    logger.info("WebSocket connected to channel: %s", channel)
    try:
        # subscribe() is a coroutine returning the async context manager —
        # awaiting it is what makes delivery actually work (#1065).
        async with await broadcast.subscribe(channel) as subscriber:
            async for message in subscriber:
                await websocket.send_text(message if isinstance(message, str) else json.dumps(message))
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        logger.info("WebSocket disconnected")


def create_app() -> Starlette:
    """Create the Starlette application"""
    routes = [
        Route("/gossip", gossip_endpoint, methods=["POST"]),
        Route("/gossip/challenge", gossip_challenge, methods=["GET"]),
        WebSocketRoute("/ws", websocket_endpoint),
    ]
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=[
                "http://127.0.0.1:8203",
                "http://localhost:8001",
                "http://localhost:8002",
                "http://localhost:8003",
                "http://localhost:8010",
                "http://127.0.0.1:8203",
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
