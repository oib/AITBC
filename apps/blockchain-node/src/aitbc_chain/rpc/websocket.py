from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aitbc.security import RateLimiter

from ..config import settings
from ..gossip import gossip_broker
from ..gossip.gossip_auth import (
    create_challenge,
    is_public_topic,
    is_restricted_topic,
    is_validator,
    verify_challenge,
)
from ..lease_tracker import lease_tracker
from ..logger import get_logger
from ..metrics import (
    gossip_auth_accepted_total,
    gossip_auth_rejected_total,
    gossip_messages_published_total,
    gossip_oversized_message_total,
    gossip_rate_limited_total,
)

router = APIRouter(prefix="", tags=["ws"])
logger = get_logger(__name__)

# Keyed on (node_id, chain_id): a node following several chains opens one
# connection per chain, and keying on node_id alone dropped all but the last.
_active_subscribers: dict[tuple[str, str], WebSocket] = {}

# Per-source-IP connection count for the public gossip websocket.
_gossip_ip_connections: dict[str, int] = {}

# Per (client_ip, topic) message rate limiter.
_gossip_msg_rate = RateLimiter(
    rate=settings.gossip_max_messages_per_minute,
    per=60,
)


def _gossip_client_ip(websocket: WebSocket) -> str:
    """Return the remote client IP for the gossip websocket.

    When uvicorn's ``--proxy-headers`` middleware is active it rewrites
    ``scope["client"]`` for us.  As a defensive fallback we also check the
    standard forwarded headers, preferring the address appended by the trusted
    reverse proxy (the right-most entry in ``X-Forwarded-For``) over the
    immediate TCP peer.
    """
    if websocket.client:
        host = websocket.client.host
    else:
        host = "unknown"

    # FastAPI's Headers object is case-insensitive.
    x_real_ip = websocket.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip.strip().split(",")[0].strip() or host

    x_forwarded_for = websocket.headers.get("x-forwarded-for")
    if x_forwarded_for:
        # The last address was appended by our trusted proxy.
        return x_forwarded_for.strip().split(",")[-1].strip() or host

    return host


async def _stream_topic(topic: str, websocket: WebSocket) -> None:
    subscription = await gossip_broker.subscribe(topic)
    try:
        while True:
            message = await subscription.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        subscription.close()


@router.websocket("/gossip/ws")
async def gossip_websocket(websocket: WebSocket) -> None:
    """Bidirectional WebSocket gossip with validator authentication.

    Clients connect with ``?topic=<topic>``. Publishing to validator-only
    topics (``blocks``, ``pbft``, ``consensus`` and any dotted sub-topic)
    requires a signed challenge/response using a key from ``VALIDATOR_SET``.
    Public topics (``transactions``, ``status``, ``mempool`` and any dotted
    sub-topic) can be published without authentication but are still
    rate-limited.

    The server bridges messages into the node's ``gossip_broker`` so remote
    validators can publish and subscribe to gossip channels over the existing
    ``/rpc`` WSS path.
    """
    topic = websocket.query_params.get("topic")
    if not topic:
        await websocket.close(code=1008)
        return

    client_ip = _gossip_client_ip(websocket)

    # Connection-level source limit.
    if _gossip_ip_connections.get(client_ip, 0) >= settings.gossip_max_concurrent_connections_per_ip:
        logger.warning("Gossip websocket connection limit for %s", client_ip)
        await websocket.close(code=1008)
        return
    _gossip_ip_connections[client_ip] = _gossip_ip_connections.get(client_ip, 0) + 1

    challenge: str | None = None
    challenge_ts: float = 0.0
    authorized = False
    authorized_address: str | None = None

    try:
        await websocket.accept()
        logger.info("WebSocket gossip subscriber connected: topic=%s client=%s", topic, client_ip)

        # If this is a restricted topic, require authentication before any publish.
        if settings.gossip_auth_enabled and is_restricted_topic(topic):
            challenge, challenge_ts = create_challenge()
            await websocket.send_json({"type": "auth_challenge", "challenge": challenge, "timestamp": challenge_ts})

        subscription = await gossip_broker.subscribe(topic, max_queue_size=100)

        async def _forward_broker_to_client() -> None:
            try:
                async for message in subscription:
                    try:
                        await websocket.send_json(message)
                    except Exception:
                        break
            except Exception as e:
                logger.warning("Error forwarding broker message for %s: %s", topic, e)

        async def _forward_client_to_broker() -> None:
            nonlocal authorized, authorized_address
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                except asyncio.TimeoutError:
                    try:
                        await websocket.send_json({"type": "ping", "timestamp": time.time()})
                    except Exception:
                        break
                    continue
                except WebSocketDisconnect:
                    break

                if len(raw) > settings.gossip_max_message_size:
                    gossip_oversized_message_total.inc()
                    await websocket.send_json({"error": "Message too large"})
                    await websocket.close(code=1009)
                    break

                if not _gossip_msg_rate.is_allowed(f"{client_ip}:{topic}"):
                    gossip_rate_limited_total.labels(reason="message_rate").inc()
                    await websocket.send_json({"error": "Rate limit exceeded"})
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"error": "Invalid JSON"})
                    continue

                # Handle authentication handshake.
                if data.get("type") == "auth_response":
                    if not settings.gossip_auth_enabled:
                        await websocket.send_json({"type": "auth_ok", "note": "auth not required"})
                        continue
                    claimed = data.get("address", "")
                    signature = data.get("signature", "")
                    client_challenge = data.get("challenge", "")
                    client_ts = data.get("timestamp", 0.0)
                    if not is_validator(claimed):
                        gossip_auth_rejected_total.labels(reason="not_validator").inc()
                        await websocket.send_json({"error": "Not a validator"})
                        await websocket.close(code=1008)
                        break
                    if client_challenge != challenge:
                        gossip_auth_rejected_total.labels(reason="challenge_mismatch").inc()
                        await websocket.send_json({"error": "Challenge mismatch"})
                        await websocket.close(code=1008)
                        break
                    if abs(time.time() - client_ts) > settings.gossip_auth_challenge_ttl:
                        gossip_auth_rejected_total.labels(reason="challenge_expired").inc()
                        await websocket.send_json({"error": "Challenge expired"})
                        await websocket.close(code=1008)
                        break
                    if verify_challenge(client_challenge, claimed, client_ts, signature):
                        authorized = True
                        authorized_address = claimed
                        gossip_auth_accepted_total.labels(address=claimed).inc()
                        await websocket.send_json({"type": "auth_ok", "address": claimed})
                        continue
                    else:
                        gossip_auth_rejected_total.labels(reason="invalid_signature").inc()
                        await websocket.send_json({"error": "Invalid signature"})
                        await websocket.close(code=1008)
                        break

                # Publishing path.
                if is_restricted_topic(topic) and not authorized:
                    gossip_auth_rejected_total.labels(reason="unauthorized_publish").inc()
                    await websocket.send_json({"error": "Validator authentication required"})
                    await websocket.close(code=1008)
                    break

                if not is_public_topic(topic) and not authorized:
                    gossip_auth_rejected_total.labels(reason="unauthorized_topic").inc()
                    await websocket.send_json({"error": "Topic not authorized"})
                    await websocket.close(code=1008)
                    break

                await gossip_broker.publish(topic, data)
                gossip_messages_published_total.labels(topic=topic).inc()

        try:
            await asyncio.gather(_forward_broker_to_client(), _forward_client_to_broker())
        except WebSocketDisconnect:
            logger.info("WebSocket gossip subscriber disconnected: topic=%s", topic)
        except Exception as e:
            logger.error("WebSocket gossip error for topic %s: %s", topic, e)
        finally:
            subscription.close()
            try:
                await websocket.close()
            except Exception:
                pass
    finally:
        _gossip_ip_connections[client_ip] = max(0, _gossip_ip_connections.get(client_ip, 1) - 1)


@router.websocket("/subscribe/ws")
async def subscription_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for follower nodes to subscribe to block pushes.

    Protocol:
    1. Client connects and sends subscription message: {"node_id": "...", "chain_id": "...", "transport": "websocket"}
    2. Server validates the subscriber has a valid lease
    3. Server subscribes to block topic and pushes new blocks to client
    4. Server sends ping every 20s, expects pong response
    """
    await websocket.accept()
    node_id: str | None = None
    # Bound before the handshake so the finally block can look up the entry
    # even when the client disconnects before sending its subscription message.
    chain_id: str = ""
    try:
        message = await websocket.receive_text()
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            await websocket.close(code=1008)
            return
        node_id = data.get("node_id")
        chain_id = data.get("chain_id", settings.chain_id)
        transport = data.get("transport", "websocket")
        if not node_id:
            await websocket.send_json({"error": "node_id is required"})
            await websocket.close(code=1008)
            return
        try:
            expiry = await lease_tracker.get_lease_expiry(node_id, chain_id)

            if expiry <= time.time():
                await websocket.send_json(
                    {"error": "No valid lease found. Register subscription first via POST /rpc/subscribe"}
                )
                await websocket.close(code=1008)
                return
        except Exception as e:
            logger.error("Failed to validate lease for %s: %s", node_id, e)
            await websocket.send_json({"error": "Failed to validate lease"})
            await websocket.close(code=1011)
            return
        _active_subscribers[node_id, chain_id] = websocket
        logger.info("WebSocket subscriber connected: %s (chain=%s, transport=%s)", node_id, chain_id, transport)
        await websocket.send_json({"status": "subscribed", "node_id": node_id, "chain_id": chain_id, "transport": transport})
        topic = f"blocks.{chain_id}"
        block_subscription = await gossip_broker.subscribe(topic)

        async def _send_blocks() -> None:
            """Send blocks to subscriber."""
            try:
                async for block_data in block_subscription:
                    if isinstance(block_data, str):
                        block_data = json.loads(block_data)
                    await websocket.send_json(block_data)
                    logger.debug("Sent block to %s", node_id)
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected for %s", node_id)
            except Exception as e:
                logger.error("Error sending block to %s: %s", node_id, e)

        async def _heartbeat() -> None:
            """Send periodic pings to keep connection alive."""
            try:
                while True:
                    await asyncio.sleep(20)
                    await websocket.send_json({"type": "ping", "timestamp": time.time()})
            except WebSocketDisconnect:  # nosec B110 - expected disconnect
                pass
            except Exception:  # nosec B110 - intentional silent cleanup
                pass

        from asyncio import create_task, wait

        block_task = create_task(_send_blocks())
        heartbeat_task = create_task(_heartbeat())
        done, pending = await wait([block_task, heartbeat_task], return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        logger.info("WebSocket subscriber disconnected: %s", node_id)
    except Exception as e:
        logger.error("WebSocket error for %s: %s", node_id, e)
    finally:
        if node_id and (node_id, chain_id) in _active_subscribers:
            del _active_subscribers[node_id, chain_id]
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("WebSocket subscriber cleanup complete: %s", node_id)
