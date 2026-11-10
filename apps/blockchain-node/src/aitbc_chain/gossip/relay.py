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
from aitbc.security import RateLimiter

from ..config import settings
from .gossip_auth import (
    channel_scope,
    create_challenge,
    is_public_topic,
    is_restricted_topic,
    publish_scope,
    verify_challenge,
)

configure_logging(level="INFO", service_name="blockchain-p2p", to_file=True)
logger = get_logger(__name__)


class BroadcastCapacityError(Exception):
    """subscribe() refused: channel/subscriber caps reached (#1537, #1538)."""


class SimpleBroadcast:
    """Simple in-memory broadcast replacement for starlette.broadcast"""

    # Per-subscriber bound (#1537): an unbounded queue let one stalled
    # WebSocket client grow memory without limit, and ``await queue.put``
    # blocked the publisher (head-of-line) behind it. A full subscriber now
    # has new messages dropped for it — same drop-on-full semantics as the
    # trading service's in-memory gossip fallback.
    _MAX_QUEUE_SIZE = 256
    # Registry bounds (#1537/#1538): public dotted-subtopic names are
    # unbounded, so without caps each invented channel minted a permanent
    # ``_subscribers`` entry. Channel keys are also reaped when their last
    # subscriber leaves (see Subscriber.__aexit__).
    _MAX_CHANNELS = 256
    _MAX_SUBSCRIBERS_PER_CHANNEL = 512
    _MAX_TOTAL_SUBSCRIBERS = 4096

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def _total_subscribers(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    async def publish(self, channel: str, message: str) -> None:
        """Publish a message to all subscribers of a channel"""
        if channel not in self._subscribers:
            return
        for queue in self._subscribers[channel]:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Dropping gossip message for slow subscriber on channel %s", channel)

    def _check_capacity(self, channel: str) -> None:
        """Raise ``BroadcastCapacityError`` when a subscription would exceed a cap."""
        is_new_channel = channel not in self._subscribers
        if is_new_channel and len(self._subscribers) >= self._MAX_CHANNELS:
            raise BroadcastCapacityError(f"channel registry full ({self._MAX_CHANNELS})")
        if not is_new_channel and len(self._subscribers[channel]) >= self._MAX_SUBSCRIBERS_PER_CHANNEL:
            raise BroadcastCapacityError(f"channel {channel!r} has {self._MAX_SUBSCRIBERS_PER_CHANNEL} subscribers")
        if self._total_subscribers() >= self._MAX_TOTAL_SUBSCRIBERS:
            raise BroadcastCapacityError(f"total subscriber cap reached ({self._MAX_TOTAL_SUBSCRIBERS})")

    async def subscribe(self, channel: str) -> Any:
        """Subscribe to a channel and return an async iterator.

        Raises ``BroadcastCapacityError`` when the channel registry, the
        per-channel subscriber list, or the total subscriber count is at
        its cap — the ws endpoint turns that into a 1013 close.
        """
        self._check_capacity(channel)
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._MAX_QUEUE_SIZE)
        self._subscribers[channel].append(queue)

        class Subscriber:
            def __init__(self, q: asyncio.Queue, subs: dict[str, list[asyncio.Queue]], ch: str) -> None:
                self.queue = q
                self.subscribers = subs
                self.channel = ch

            async def __aenter__(self) -> "Subscriber":
                return self

            async def __aexit__(self, *args: Any) -> None:
                queues = self.subscribers.get(self.channel)
                if queues is not None and self.queue in queues:
                    queues.remove(self.queue)
                # Reap the channel key once its last subscriber leaves —
                # otherwise every invented dotted subtopic stayed in the
                # registry forever (#1538).
                if queues is not None and not queues:
                    self.subscribers.pop(self.channel, None)

            def __aiter__(self) -> "Subscriber":
                return self

            async def __anext__(self) -> str:
                return await self.queue.get()  # type: ignore[no-any-return]

        return Subscriber(queue, self._subscribers, channel)


broadcast = SimpleBroadcast()

# Per-source-IP publish throttle for POST /gossip (#1591): public topics
# accept unauthenticated publishes, so without a limit one client could
# fan out arbitrary volume to every subscriber queue. Same sliding-window
# RateLimiter the challenge mint path uses.
_publish_rate = RateLimiter(rate=120, per=60)

# Per-source-IP WebSocket connection cap for /ws (#1537): public-channel
# subscribes need no credentials, so sockets are the scarce resource.
_MAX_WS_CONNECTIONS_PER_IP = 64
_ws_ip_counts: dict[str, int] = {}


class _BodyTooLarge(Exception):
    """POST /gossip body exceeded ``gossip_relay_max_body_bytes`` (#1591)."""


async def _read_body_capped(request: Any, max_bytes: int) -> bytes:
    """Read the request body with a hard byte cap.

    ``request.json()`` buffers the entire body first — the Content-Length
    check alone is not enough (chunked/missing headers), so the streamed
    read enforces the bound on the bytes actually received.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise _BodyTooLarge(f"body exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def gossip_challenge(request: Any) -> JSONResponse:
    """Issue a challenge for publishers of validator-restricted topics.

    Same pattern as the node's /rpc/gossip/ws (#1065): the client signs
    {challenge, address, timestamp} with its validator key and posts the
    signature with the message.
    """
    issued = create_challenge(getattr(request.client, "host", "") if request.client else "")
    if issued is None:
        return JSONResponse({"status": "error", "message": "Challenge rate limited"}, status_code=429)
    challenge, ts = issued
    return JSONResponse({"challenge": challenge, "timestamp": ts})


def _publisher_authenticated(data: Any, scope: str) -> bool:
    """True when the body carries a valid validator challenge response.

    ``scope`` is derived HERE from the actual request — the signature must
    cover this exact payload/topic, not just the challenge (#1128).
    """
    try:
        return bool(
            verify_challenge(
                str(data.get("challenge", "")),
                str(data.get("address", "")),
                float(data.get("timestamp", 0)),
                str(data.get("signature", "")),
                scope,
            )
        )
    except (TypeError, ValueError):
        return False


async def gossip_endpoint(request: Any) -> JSONResponse:
    """HTTP endpoint for publishing gossip messages"""
    client_ip = request.client.host if request.client else ""
    if not _publish_rate.is_allowed(f"publish:{client_ip}"):
        return JSONResponse({"status": "error", "message": "Rate limit exceeded"}, status_code=429)
    # Cheap reject on a declared oversize body before reading anything;
    # the streamed read below is the authoritative bound (#1591).
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > settings.gossip_relay_max_body_bytes:
        return JSONResponse({"status": "error", "message": "Body too large"}, status_code=413)
    try:
        body = await _read_body_capped(request, settings.gossip_relay_max_body_bytes)
    except _BodyTooLarge:
        return JSONResponse({"status": "error", "message": "Body too large"}, status_code=413)
    try:
        data = json.loads(body)
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)
    # A valid-JSON non-object body used to reach data.get() and 500 (#1591).
    if not isinstance(data, dict):
        return JSONResponse({"status": "error", "message": "Body must be a JSON object"}, status_code=400)
    channel = str(data.get("channel", "blockchain"))
    message = data.get("message")
    if not message:
        return JSONResponse({"status": "error", "message": "No message provided"}, status_code=400)
    # Publishing to validator-restricted topics (blocks.*, pbft.*,
    # consensus.*) needs the signed challenge; unknown channels are
    # rejected outright — the relay used to publish anything to
    # anyone (#1065).
    if is_restricted_topic(channel):
        if not _publisher_authenticated(data, publish_scope(channel, message)):
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
    # Unknown channels are refused outright — same policy as POST /gossip
    # (#1065). Public dotted-subtopic names stay valid, but the registry
    # caps in SimpleBroadcast bound how many can exist at once (#1538).
    if not is_public_topic(channel) and not is_restricted_topic(channel):
        await websocket.close(code=1008)
        logger.warning("Rejected subscribe to unknown channel: %s", channel)
        return
    # Restricted topics need the validator challenge on SUBSCRIBE too —
    # publish-side auth alone leaves the streams readable (#1065). The
    # caller fetches a challenge from GET /gossip/challenge and signs it.
    if is_restricted_topic(channel) and not _publisher_authenticated(websocket.query_params, channel_scope(channel)):
        await websocket.close(code=1008)
        logger.warning("Rejected unauthenticated restricted subscribe: %s", channel)
        return
    client_ip = websocket.client.host if websocket.client else ""
    if _ws_ip_counts.get(client_ip, 0) >= _MAX_WS_CONNECTIONS_PER_IP:
        await websocket.close(code=1008)
        logger.warning("WebSocket connection cap reached for %s", client_ip)
        return
    _ws_ip_counts[client_ip] = _ws_ip_counts.get(client_ip, 0) + 1
    await websocket.accept()
    logger.info("WebSocket connected to channel: %s", channel)
    try:
        # subscribe() is a coroutine returning the async context manager —
        # awaiting it is what makes delivery actually work (#1065).
        try:
            subscriber_cm = await broadcast.subscribe(channel)
        except BroadcastCapacityError as e:
            await websocket.close(code=1013)
            logger.warning("Subscribe refused on %s: %s", channel, e)
            return
        async with subscriber_cm as subscriber:
            async for message in subscriber:
                await websocket.send_text(message if isinstance(message, str) else json.dumps(message))
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        remaining = _ws_ip_counts.get(client_ip, 1) - 1
        if remaining > 0:
            _ws_ip_counts[client_ip] = remaining
        else:
            _ws_ip_counts.pop(client_ip, None)
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
