from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aitbc.rate_limiting import client_ip_from_peer_and_headers
from aitbc.security import RateLimiter

from ..config import settings
from ..gossip import (
    BroadcastGossipBackend,
    GossipBackend,
    GossipBroker,
    InMemoryGossipBackend,
    MeshGossipBackend,
    WebsocketGossipBackend,
    gossip_broker,
)
from ..gossip._internal import _peer_name
from ..gossip.gossip_auth import (
    RESTRICTED_GOSSIP_TOPICS,
    channel_scope,
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
    gossip_authenticated_connections,
    gossip_messages_published_total,
    gossip_open_connections,
    gossip_oversized_message_total,
    gossip_rate_limited_total,
    metrics_registry,
)

router = APIRouter(prefix="", tags=["ws"])
logger = get_logger(__name__)

# Keyed on (node_id, chain_id): a node following several chains opens one
# connection per chain, and keying on node_id alone dropped all but the last.
_active_subscribers: dict[tuple[str, str], WebSocket] = {}

# Per-(client_ip, chain_id) connection count for the public gossip websocket.
# Keying on the chain as well keeps one chain's connection budget from being
# consumed by another chain's clients (#1159).
_gossip_ip_connections: dict[tuple[str, str], int] = {}

# Lazily-created per-chain brokers for chains this process serves beyond
# ``settings.chain_id``. The default chain keeps using the module-global
# ``gossip_broker`` wired by main.py; every other chain MUST resolve its
# backend from explicit per-chain config (GOSSIP_BACKENDS entries or
# chain-tagged GOSSIP_MESH_PEER_URLS) — never the shared default backend,
# which would route one chain's topics through another chain's bus (#1159).
_chain_brokers: dict[str, GossipBroker] = {}

# Per (client_ip, chain, topic CLASS) message rate limiter. The class, not the
# raw topic string, is the key: dotted public subtopics are unbounded, and a
# bucket per topic string multiplied the budget by the number of topics a
# client cared to open (#1243). See _gossip_rate_key.
_gossip_msg_rate = RateLimiter(
    rate=settings.gossip_max_messages_per_minute,
    per=60,
)

# Bound on websocket accept/close so a vanished client cannot wedge the
# handler before the per-IP counter is released (#1158).
_GOSSIP_WS_OP_TIMEOUT = 10.0


async def _gossip_ws_close(websocket: WebSocket, code: int | None = None) -> None:
    try:
        if code is None:
            await asyncio.wait_for(websocket.close(), timeout=_GOSSIP_WS_OP_TIMEOUT)
        else:
            await asyncio.wait_for(websocket.close(code=code), timeout=_GOSSIP_WS_OP_TIMEOUT)
    except Exception:  # nosec
        pass


async def _gossip_ws_send_json(websocket: WebSocket, payload: object) -> None:
    """send_json bounded by _GOSSIP_WS_OP_TIMEOUT.

    A peer that stops reading (no RST/FIN — NAT churn, firewall) would
    otherwise park a gossip forwarder on send_json forever, wedging the
    handler and the per-IP connection slot (RPC-GOSSIP-SENDJSON-UNBOUNDED-1).
    On timeout asyncio.wait_for cancels the send; callers treat it like any
    other send failure and unwind so _gossip_ip_connections is released.
    """
    await asyncio.wait_for(websocket.send_json(payload), timeout=_GOSSIP_WS_OP_TIMEOUT)


def _gossip_client_ip(websocket: WebSocket) -> str:
    """Return the client IP that keys the gossip connection and rate limits.

    The TCP peer is the key unless it is a trusted proxy
    (``AITBC_TRUSTED_PROXIES``, default loopback — the node's own nginx); only
    then are ``X-Real-IP`` / the right-most untrusted ``X-Forwarded-For``
    entry honoured. A client connecting directly can no longer rotate those
    headers to mint a fresh per-IP connection slot, message bucket and
    challenge-mint bucket per connection (#1241). Behind uvicorn
    ``--proxy-headers`` ``scope["client"]`` is already the real client.

    Per-process state: ``_gossip_ip_connections`` and ``_gossip_msg_rate``
    live in each uvicorn worker's memory, so under ``--workers N`` the
    effective per-IP ceilings are N x the configured values (#1241).
    """
    return client_ip_from_peer_and_headers(
        websocket.client.host if websocket.client else "",
        websocket.headers,
    )


def _gossip_rate_class(topic: str) -> str:
    """Collapse a gossip topic to the bounded class its rate budget is shared in.

    ``public``: every public root (``transactions``/``status``/``mempool`` and
    any dotted subtopic) — the only topics an unauthenticated client may
    publish to, so one source gets exactly one public budget however many
    subtopics it invents. A restricted root keeps its own bucket (``blocks``,
    ``pbft``, ``consensus``), so a flood on one class cannot starve a
    validator's consensus traffic. Anything else is ``other`` (reachable only
    by an authenticated validator, or by an unauthenticated client that is
    closed on its first message). At most five classes exist per (ip, chain).
    """
    if is_public_topic(topic):
        return "public"
    for root in RESTRICTED_GOSSIP_TOPICS:
        if topic == root or topic.startswith(root + "."):
            return root
    return "other"


def _gossip_rate_key(client_ip: str, chain_id: str, topic: str) -> str:
    """Key of the per-message rate bucket: identity x chain x topic class (#1243)."""
    return f"{client_ip}:{chain_id}:{_gossip_rate_class(topic)}"


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


def _connectable_chain_ids() -> list[str]:
    """Chains this process can actually serve gossip for.

    A chain is connectable when it is declared in ``supported_chains`` AND
    has a resolvable backend: the default ``chain_id`` (wired by main.py) or
    an explicit ``GOSSIP_BACKENDS`` entry. Chains named in
    ``supported_chains`` without backend config are NOT connectable — the
    ``?chain=`` param for them is rejected rather than silently routed
    through another chain's bus (#1159).
    """
    backend_chains = set(settings.gossip_backend_map())
    return [c for c in settings.served_chain_ids() if c == settings.chain_id or c in backend_chains]


def _resolve_chain_id(websocket: WebSocket) -> str | None:
    """Resolve the ``?chain=<id>`` query param to a connectable chain id.

    Returns ``None`` when the request must be rejected: an explicit chain
    the process does not connectably serve, or a missing param on a host
    serving multiple chains — there is deliberately no silent default
    there (#1159). Single-chain hosts keep the legacy behaviour: no param
    means ``chain_id``.
    """
    param = websocket.query_params.get("chain") or websocket.query_params.get("chain_id")
    connectable = _connectable_chain_ids()
    if param:
        return param if param in connectable else None
    if len(connectable) == 1:
        return connectable[0]
    return None


def _topic_targets_other_chain(topic: str, chain_id: str) -> bool:
    """True when ``topic`` is explicitly namespaced to a different connectable chain.

    Only CONNECTABLE chains count: a suffix naming a chain this host does not
    serve gossip for is just a topic name on this chain's bus, not a cross-chain
    route. Chain ids may themselves contain dots (``ait-testchain.local``), so
    the match is on the full ``"." + chain_id`` suffix — never a naive
    last-segment split.
    """
    return any(other != chain_id and topic.endswith("." + other) for other in _connectable_chain_ids())


def _backend_from_url(url: str, chain_id: str | None = None) -> GossipBackend | None:
    """Build a gossip backend from a ``GOSSIP_BACKENDS`` URL by scheme."""
    scheme = url.split("://", 1)[0].lower() if "://" in url else url.strip().lower()
    if scheme in {"redis", "rediss"}:
        return BroadcastGossipBackend(url)
    if scheme in {"wss", "ws"}:
        return WebsocketGossipBackend(url, chain_id=chain_id)
    if scheme in {"memory", "inmemory", "local"}:
        # Per-process only — a dev/test hatch, never a cross-node bus.
        return InMemoryGossipBackend()
    return None


def _backend_for_chain(chain_id: str) -> GossipBackend | None:
    """Resolve the backend for a non-default chain from per-chain config only.

    Resolution order (megaplan §2): a ``GOSSIP_BACKENDS`` ``chain_id:<url>``
    entry, optionally combined with that chain's tagged ``GOSSIP_MESH_PEER_URLS``
    into a mesh backend. Chains with tagged peers but no local-bus entry are
    unserved — a mesh backend cannot be built without its local bus, and
    falling back to the default backend would leak topics across chains.
    """
    local_url = settings.gossip_backend_map().get(chain_id)
    peer_urls = settings.mesh_peer_urls_for_chain(chain_id)
    if not local_url:
        return None
    local = _backend_from_url(local_url, chain_id=chain_id)
    if local is None:
        return None
    if not peer_urls:
        return local
    peers: dict[str, GossipBackend] = {}
    for url in peer_urls:
        name = _peer_name(url)
        if name in peers:
            return None
        peers[name] = WebsocketGossipBackend(url, chain_id=chain_id)
    return MeshGossipBackend(local, peers)


def _broker_for_chain(chain_id: str) -> GossipBroker | None:
    """Return the GossipBroker serving ``chain_id``, or None if unserved."""
    if chain_id == settings.chain_id:
        return gossip_broker
    broker = _chain_brokers.get(chain_id)
    if broker is not None:
        return broker
    backend = _backend_for_chain(chain_id)
    if backend is None:
        return None
    broker = GossipBroker(backend)
    _chain_brokers[chain_id] = broker
    return broker


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
        await _gossip_ws_close(websocket, code=1008)
        return

    chain_id = _resolve_chain_id(websocket)
    if chain_id is None:
        await _gossip_ws_close(websocket, code=1008)
        return
    if _topic_targets_other_chain(topic, chain_id):
        logger.warning("Gossip websocket rejected cross-chain topic %s on chain %s", topic, chain_id)
        await _gossip_ws_close(websocket, code=1008)
        return
    broker = _broker_for_chain(chain_id)
    if broker is None:
        logger.warning("Gossip websocket rejected: no gossip backend for chain %s", chain_id)
        await _gossip_ws_close(websocket, code=1008)
        return

    client_ip = _gossip_client_ip(websocket)
    conn_key = (client_ip, chain_id)

    # Connection-level source limit, per (ip, chain).
    if _gossip_ip_connections.get(conn_key, 0) >= settings.gossip_max_concurrent_connections_per_ip:
        logger.warning("Gossip websocket connection limit for %s on chain %s", client_ip, chain_id)
        await _gossip_ws_close(websocket, code=1008)
        return
    _gossip_ip_connections[conn_key] = _gossip_ip_connections.get(conn_key, 0) + 1
    gossip_open_connections.inc()

    challenge: str | None = None
    challenge_ts: float = 0.0
    authorized = False
    authorized_address: str | None = None

    try:
        try:
            await asyncio.wait_for(websocket.accept(), timeout=_GOSSIP_WS_OP_TIMEOUT)
        except TimeoutError:
            logger.warning("Gossip websocket accept timed out for %s", client_ip)
            await _gossip_ws_close(websocket, code=1011)
            return
        logger.info("WebSocket gossip subscriber connected: topic=%s chain=%s client=%s", topic, chain_id, client_ip)

        # If this is a restricted topic, require authentication before any publish.
        if settings.gossip_auth_enabled and is_restricted_topic(topic):
            issued = create_challenge(client_ip)
            if issued is None:
                gossip_auth_rejected_total.labels(reason="challenge_rate_limited").inc()
                await _gossip_ws_send_json(websocket, {"error": "Challenge rate limited"})
                await _gossip_ws_close(websocket, code=1008)
                return
            challenge, challenge_ts = issued
            await _gossip_ws_send_json(
                websocket, {"type": "auth_challenge", "challenge": challenge, "timestamp": challenge_ts}
            )

        subscription = await broker.subscribe(topic, max_queue_size=100)

        async def _forward_broker_to_client() -> None:
            try:
                async for message in subscription:
                    try:
                        await _gossip_ws_send_json(websocket, message)
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
                        await _gossip_ws_send_json(websocket, {"type": "ping", "timestamp": time.time()})
                    except Exception:
                        break
                    continue
                except WebSocketDisconnect:
                    break

                if len(raw) > settings.gossip_max_message_size:
                    gossip_oversized_message_total.inc()
                    await _gossip_ws_send_json(websocket, {"error": "Message too large"})
                    await _gossip_ws_close(websocket, code=1009)
                    break

                if not _gossip_msg_rate.is_allowed(_gossip_rate_key(client_ip, chain_id, topic)):
                    gossip_rate_limited_total.labels(reason="message_rate").inc()
                    await _gossip_ws_send_json(websocket, {"error": "Rate limit exceeded"})
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await _gossip_ws_send_json(websocket, {"error": "Invalid JSON"})
                    continue

                # Handle authentication handshake.
                if data.get("type") == "auth_response":
                    if not settings.gossip_auth_enabled:
                        await _gossip_ws_send_json(websocket, {"type": "auth_ok", "note": "auth not required"})
                        continue
                    claimed = data.get("address", "")
                    signature = data.get("signature", "")
                    client_challenge = data.get("challenge", "")
                    client_ts = data.get("timestamp", 0.0)
                    if not is_validator(claimed):
                        gossip_auth_rejected_total.labels(reason="not_validator").inc()
                        await _gossip_ws_send_json(websocket, {"error": "Not a validator"})
                        await _gossip_ws_close(websocket, code=1008)
                        break
                    if client_challenge != challenge:
                        gossip_auth_rejected_total.labels(reason="challenge_mismatch").inc()
                        await _gossip_ws_send_json(websocket, {"error": "Challenge mismatch"})
                        await _gossip_ws_close(websocket, code=1008)
                        break
                    if abs(time.time() - client_ts) > settings.gossip_auth_challenge_ttl:
                        gossip_auth_rejected_total.labels(reason="challenge_expired").inc()
                        await _gossip_ws_send_json(websocket, {"error": "Challenge expired"})
                        await _gossip_ws_close(websocket, code=1008)
                        break
                    if verify_challenge(
                        client_challenge,
                        claimed,
                        client_ts,
                        signature,
                        channel_scope(topic, chain_id),
                        legacy_scope=channel_scope(topic),
                    ):
                        if not authorized:
                            gossip_authenticated_connections.labels(address=claimed).inc()
                        authorized = True
                        authorized_address = claimed
                        gossip_auth_accepted_total.labels(address=claimed).inc()
                        await _gossip_ws_send_json(websocket, {"type": "auth_ok", "address": claimed})
                        continue
                    else:
                        gossip_auth_rejected_total.labels(reason="invalid_signature").inc()
                        await _gossip_ws_send_json(websocket, {"error": "Invalid signature"})
                        await _gossip_ws_close(websocket, code=1008)
                        break

                # Publishing path.
                if is_restricted_topic(topic) and not authorized:
                    gossip_auth_rejected_total.labels(reason="unauthorized_publish").inc()
                    await _gossip_ws_send_json(websocket, {"error": "Validator authentication required"})
                    await _gossip_ws_close(websocket, code=1008)
                    break

                if not is_public_topic(topic) and not authorized:
                    gossip_auth_rejected_total.labels(reason="unauthorized_topic").inc()
                    await _gossip_ws_send_json(websocket, {"error": "Topic not authorized"})
                    await _gossip_ws_close(websocket, code=1008)
                    break

                try:
                    await broker.publish(topic, data)
                    gossip_messages_published_total.labels(topic=topic).inc()
                except Exception as e:  # noqa: BLE001 - one bad publish must not close the socket
                    # A broker-side failure (e.g. an ACL-denied topic) loses
                    # this message — but must not close the connection: the
                    # same socket carries other topics and the receive path,
                    # and tearing it down on one bad publish churns the whole
                    # attestation transport.
                    logger.warning("Broker publish failed for topic %s — message dropped: %s", topic, e)
                    metrics_registry.increment("gossip_broker_publish_failed_total")
                    continue

        from asyncio import create_task, wait

        broker_task = create_task(_forward_broker_to_client())
        client_task = create_task(_forward_client_to_broker())
        try:
            done, pending = await wait([broker_task, client_task], return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                exc = None if task.cancelled() else task.exception()
                if isinstance(exc, (WebSocketDisconnect, asyncio.TimeoutError)):
                    # TimeoutError = bounded send_json hit _GOSSIP_WS_OP_TIMEOUT
                    # on a peer that stopped reading — same teardown as a
                    # disconnect (#1165).
                    logger.info("WebSocket gossip subscriber disconnected: topic=%s", topic)
                elif exc is not None:
                    logger.error("WebSocket gossip error for topic %s: %s", topic, exc)
        except WebSocketDisconnect:
            logger.info("WebSocket gossip subscriber disconnected: topic=%s", topic)
        except Exception as e:
            logger.error("WebSocket gossip error for topic %s: %s", topic, e)
        finally:
            for task in (broker_task, client_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(broker_task, client_task, return_exceptions=True)
            subscription.close()
            await _gossip_ws_close(websocket)
    finally:
        _gossip_ip_connections[conn_key] = max(0, _gossip_ip_connections.get(conn_key, 1) - 1)
        gossip_open_connections.dec()
        if authorized_address:
            gossip_authenticated_connections.labels(address=authorized_address).dec()


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
        broker = _broker_for_chain(chain_id)
        if broker is None:
            await websocket.send_json({"error": "Unsupported chain"})
            await websocket.close(code=1008)
            return
        block_subscription = await broker.subscribe(topic)

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
            except WebSocketDisconnect:  # expected disconnect
                pass
            # intentional silent cleanup
            except Exception:  # nosec B110
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
        except Exception:  # nosec
            pass
        logger.info("WebSocket subscriber cleanup complete: %s", node_id)
