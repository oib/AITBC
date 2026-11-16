from __future__ import annotations

import asyncio
import json
import time
from typing import Any

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
    TopicSubscription,
    WebsocketGossipBackend,
    gossip_broker,
)
from ..gossip._internal import _message_id, _peer_name, bounded_topic_label
from ..gossip.gossip_auth import (
    channel_scope,
    create_challenge,
    gossip_topic_class,
    is_public_topic,
    is_restricted_topic,
    is_validator,
    verify_challenge,
)
from ..gossip.telemetry import (
    gossip_event,
    gossip_ws_echo_forward_failed_total,
    gossip_ws_echo_forward_total,
    gossip_ws_rx_publish_total,
    gossip_ws_subscriber_queue_depth,
)
from ..lease_tracker import lease_tracker
from ..logger import get_logger
from ..metrics import (
    gossip_auth_accepted_total,
    gossip_auth_membership_unconfigured_total,
    gossip_auth_rejected_total,
    gossip_authenticated_connections,
    gossip_messages_published_total,
    gossip_open_connections,
    gossip_oversized_message_total,
    gossip_rate_limited_total,
    gossip_ws_open_connections,
    gossip_ws_rejected_total,
    metrics_registry,
)
from . import peer_keys
from .escrow_routes import rpc_fleet_key_accepted, rpc_peer_key_accepted

router = APIRouter(prefix="", tags=["ws"])
logger = get_logger(__name__)

# Keyed on (node_id, chain_id): a node following several chains opens one
# connection per chain, and keying on node_id alone dropped all but the last.
_active_subscribers: dict[tuple[str, str], WebSocket] = {}

# Per-(client_ip, chain_id) connection count for the public gossip websocket.
# Keying on the chain as well keeps one chain's connection budget from being
# consumed by another chain's clients (#1159).
_gossip_ip_connections: dict[tuple[str, str], int] = {}

# Per-source-IP total across chains, kept alongside the per-(ip, chain) map so
# the optional aggregate ceiling (GOSSIP_MAX_CONNECTIONS_PER_IP_TOTAL) is O(1).
_gossip_ip_total: dict[str, int] = {}

# Per-source-IP connection count for /subscribe/ws (#1587). The gossip ws
# path has had this since #1159; the block-push endpoint had none, so one
# IP could hold unlimited sockets (each with a broker subscription and two
# forwarder tasks). Keyed on IP alone — the chain is only known after the
# handshake frame, and the slot must be held from accept onward.
_subscribe_ip_connections: dict[str, int] = {}


def _acquire_subscribe_ip_slot(client_ip: str) -> bool:
    """Take a /subscribe/ws slot for ``client_ip``; False when at the cap."""
    if _subscribe_ip_connections.get(client_ip, 0) >= settings.subscribe_ws_max_connections_per_ip:
        return False
    _subscribe_ip_connections[client_ip] = _subscribe_ip_connections.get(client_ip, 0) + 1
    return True


def _release_subscribe_ip_slot(client_ip: str) -> None:
    remaining = _subscribe_ip_connections.get(client_ip, 1) - 1
    if remaining > 0:
        _subscribe_ip_connections[client_ip] = remaining
    else:
        _subscribe_ip_connections.pop(client_ip, None)


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
    except Exception as e:  # noqa: BLE001,S110 - close is best-effort during teardown  # nosec
        logger.debug("gossip websocket close failed: %s", type(e).__name__)


async def _gossip_ws_send_json(websocket: WebSocket, payload: object) -> None:
    """send_json bounded by _GOSSIP_WS_OP_TIMEOUT.

    A peer that stops reading (no RST/FIN — NAT churn, firewall) would
    otherwise park a gossip forwarder on send_json forever, wedging the
    handler and the per-IP connection slot (RPC-GOSSIP-SENDJSON-UNBOUNDED-1).
    On timeout asyncio.wait_for cancels the send; callers treat it like any
    other send failure and unwind so _gossip_ip_connections is released.
    """
    await asyncio.wait_for(websocket.send_json(payload), timeout=_GOSSIP_WS_OP_TIMEOUT)


def _rx_publish_extra_fields(data: object) -> dict[str, object]:
    """R7 publisher-identity + R3 lag fields for ``rx_publish`` records (#1308).

    ``publisher``: first identity-ish field present — transport peer stays in
    ``peer=``; this is the gossip-level signer/proposer when the payload
    carries one. ``lag_ms``: only emitted when the message carries a recent
    epoch ``timestamp`` — absent or stale (>1h, clock-skewed, or non-send-time
    timestamps like block time) fields emit nothing rather than mislead.
    """
    extra: dict[str, object] = {}
    if not isinstance(data, dict):
        return extra
    publisher = data.get("proposer") or data.get("validator") or data.get("publisher") or data.get("signer")
    if publisher:
        extra["publisher"] = str(publisher)[:64]
    ts = data.get("timestamp")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        lag = time.time() - float(ts)
        if 0.0 <= lag < 3600.0:
            extra["lag_ms"] = round(lag * 1000.0, 1)
    return extra


def _subscription_queue_depth(subscription: object) -> int | None:
    """Best-effort subscriber queue depth for telemetry (#1308 respin-3 fix).

    ``TopicSubscription.queue`` is part of the production contract, but test
    doubles and alternate backends may not carry it — telemetry must never
    break the publish path, so a missing/unreadable queue yields ``None``
    (gauge skipped, event field null) instead of raising.
    """
    queue = getattr(subscription, "queue", None)
    qsize = getattr(queue, "qsize", None)
    if qsize is None:
        return None
    try:
        return int(qsize())
    except Exception as e:  # noqa: BLE001 - queue probe failure reports unknown depth
        logger.debug("subscription queue size probe failed: %s", type(e).__name__)
        return None


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
    """Bounded class a topic's rate budget is shared in (see ``gossip_topic_class``).

    One source gets one public budget however many subtopics it invents; a
    restricted root keeps its own bucket so a flood on one class cannot
    starve a validator's consensus traffic (#1243).
    """
    return gossip_topic_class(topic)


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
        subscription.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous


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


def _acquire_ip_connection(conn_key: tuple[str, str]) -> str | None:
    """Take a connection slot for ``conn_key`` or return the refusal reason.

    ``conn_cap``: the per-(ip, chain) limit. ``conn_cap_total``: the optional
    per-IP ceiling across chains (``GOSSIP_MAX_CONNECTIONS_PER_IP_TOTAL``,
    0 = off). Nothing is recorded on a refusal.
    """
    client_ip = conn_key[0]
    if _gossip_ip_connections.get(conn_key, 0) >= settings.gossip_max_concurrent_connections_per_ip:
        return "conn_cap"
    total_cap = settings.gossip_max_connections_per_ip_total
    if total_cap > 0 and _gossip_ip_total.get(client_ip, 0) >= total_cap:
        return "conn_cap_total"
    _gossip_ip_connections[conn_key] = _gossip_ip_connections.get(conn_key, 0) + 1
    _gossip_ip_total[client_ip] = _gossip_ip_total.get(client_ip, 0) + 1
    return None


def _release_ip_connection(conn_key: tuple[str, str]) -> None:
    """Drop one connection from ``conn_key``'s count; delete entries at zero.

    Leaving zero-count entries behind grew ``_gossip_ip_connections`` by one
    key per distinct (ip, chain) for the process lifetime (#1256, #1159 G4);
    the per-IP total map gets the same treatment.
    """
    remaining = _gossip_ip_connections.get(conn_key, 1) - 1
    if remaining > 0:
        _gossip_ip_connections[conn_key] = remaining
    else:
        _gossip_ip_connections.pop(conn_key, None)
    client_ip = conn_key[0]
    total = _gossip_ip_total.get(client_ip, 1) - 1
    if total > 0:
        _gossip_ip_total[client_ip] = total
    else:
        _gossip_ip_total.pop(client_ip, None)


def _chain_label(chain_id: str | None) -> str:
    """Bounded metric label for a chain: a connectable chain id, else "unknown"."""
    if chain_id and chain_id in _connectable_chain_ids():
        return chain_id
    return "unknown"


def _note_rejection(chain_id: str | None, topic: str, reason: str) -> None:
    """Count a refusal on ``gossip_ws_rejected_total`` with bounded labels only."""
    gossip_ws_rejected_total.labels(chain=_chain_label(chain_id), topic_class=gossip_topic_class(topic), reason=reason).inc()


def _membership_refused(chain_id: str, topic: str) -> bool:
    """#1259 (D2 option P) per-chain validator-membership guard.

    The validator set is process-global, so a connectable chain other than the
    default ``chain_id`` would be authenticated against the DEFAULT chain's
    set. Counted whenever gossip auth is on; refused only with
    ``gossip_auth_require_chain_membership`` and no shared-validators opt-in.
    Single-chain hosts and the default chain never hit this.
    """
    if not settings.gossip_auth_enabled:
        return False
    if chain_id == settings.chain_id or chain_id in settings.gossip_shared_validator_chain_ids():
        return False
    gossip_auth_membership_unconfigured_total.labels(chain=_chain_label(chain_id)).inc()
    if not settings.gossip_auth_require_chain_membership:
        return False
    logger.warning("Gossip websocket rejected: no validator membership configured for chain %s", chain_id)
    _note_rejection(chain_id, topic, "chain_membership_unconfigured")
    return True


def _auth_rejected(reason: str, chain_id: str, topic: str) -> None:
    """Existing per-reason auth counter plus the per-chain ``auth`` series."""
    gossip_auth_rejected_total.labels(reason=reason).inc()
    _note_rejection(chain_id, topic, "auth")


_msg_total_limiter: RateLimiter | None = None


def _message_total_allowed(client_ip: str) -> bool:
    """Optional per-IP message ceiling across chains and classes.

    ``GOSSIP_MAX_MESSAGES_PER_MINUTE_TOTAL`` 0 = off. The limiter is built on
    first use and rebuilt if the configured rate changes, so the value is read
    at use time, not frozen at import.
    """
    global _msg_total_limiter
    rate = settings.gossip_max_messages_per_minute_total
    if rate <= 0:
        return True
    if _msg_total_limiter is None or _msg_total_limiter.rate != rate:
        _msg_total_limiter = RateLimiter(rate=rate, per=60)
    return _msg_total_limiter.is_allowed(f"total:{client_ip}")


async def shutdown_chain_brokers(timeout: float = 5.0) -> None:
    """Shut down every lazily-created per-chain broker (#1256, #1159 G3).

    Called from the app lifespan beside the default ``gossip_broker`` shutdown.
    Each broker gets its own bounded wait and a failure never blocks the rest,
    so one stuck chain cannot keep the others' tasks/sockets alive. The
    registry is emptied first, so a connection racing the shutdown builds a
    fresh broker rather than reusing one that is mid-teardown.
    """
    brokers = list(_chain_brokers.items())
    _chain_brokers.clear()

    async def _one(chain_id: str, broker: GossipBroker) -> None:
        try:
            await asyncio.wait_for(broker.shutdown(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Gossip broker shutdown timed out for chain %s", chain_id)
        except Exception as exc:
            logger.warning("Failed to shut down gossip broker for chain %s: %s", chain_id, exc)

    await asyncio.gather(*(_one(c, b) for c, b in brokers))


class _GossipConnState:
    """Mutable per-connection state shared by the gossip ws forwarders.

    Carries what the old nested forwarders closed over via ``nonlocal``:
    the deferred broker subscription, the validator challenge pair, and
    the auth outcomes the teardown ``finally`` reads. A plain class (not a
    dataclass): tests re-execute this module under fresh worker-module
    names, where dataclass field resolution cannot see ``sys.modules``.
    """

    def __init__(self, websocket: WebSocket, topic: str, chain_id: str, client_ip: str, broker: GossipBroker) -> None:
        self.websocket = websocket
        self.topic = topic
        self.chain_id = chain_id
        self.client_ip = client_ip
        self.broker = broker
        self.subscription: TopicSubscription | None = None
        self.subscription_ready = asyncio.Event()
        self.challenge: str | None = None
        self.challenge_ts: float = 0.0
        self.authorized = False
        self.authorized_address: str | None = None
        # #1874: peer-key credential for public-topic publish (peer_auth frame).
        self.peer_authorized = False


async def _gossip_admit(websocket: WebSocket, topic: str) -> tuple[str, GossipBroker] | None:
    """Resolve chain/backend for ``topic``; close + return None when refused.

    Every refusal path records its ``gossip_ws_rejected_total`` series and
    closes with 1008 before returning, exactly as the inline pre-checks did.
    """
    chain_id = _resolve_chain_id(websocket)
    if chain_id is None:
        _note_rejection(None, topic, "unknown_chain")
        await _gossip_ws_close(websocket, code=1008)
        return None
    if _topic_targets_other_chain(topic, chain_id):
        logger.warning("Gossip websocket rejected cross-chain topic %s on chain %s", topic, chain_id)
        _note_rejection(chain_id, topic, "cross_chain_topic")
        await _gossip_ws_close(websocket, code=1008)
        return None
    if _membership_refused(chain_id, topic):
        await _gossip_ws_close(websocket, code=1008)
        return None
    broker = _broker_for_chain(chain_id)
    if broker is None:
        logger.warning("Gossip websocket rejected: no gossip backend for chain %s", chain_id)
        _note_rejection(chain_id, topic, "no_backend")
        await _gossip_ws_close(websocket, code=1008)
        return None
    return chain_id, broker


async def _gossip_acquire_slot(websocket: WebSocket, client_ip: str, chain_id: str, topic: str) -> tuple[str, str] | None:
    """Take the per-(ip, chain) connection slot; None = refused (closed)."""
    conn_key = (client_ip, chain_id)
    # Connection-level source limit, per (ip, chain) plus the optional per-IP total.
    refused = _acquire_ip_connection(conn_key)
    if refused is not None:
        logger.warning("Gossip websocket connection limit (%s) for %s on chain %s", refused, client_ip, chain_id)
        _note_rejection(chain_id, topic, refused)
        await _gossip_ws_close(websocket, code=1008)
        return None
    return conn_key


async def _gossip_accept_and_challenge(state: _GossipConnState) -> bool:
    """Accept the socket (bounded) and issue the validator challenge.

    False means the socket was already closed and the handler must return.
    """
    try:
        await asyncio.wait_for(state.websocket.accept(), timeout=_GOSSIP_WS_OP_TIMEOUT)
    except TimeoutError:
        logger.warning("Gossip websocket accept timed out for %s", state.client_ip)
        await _gossip_ws_close(state.websocket, code=1011)
        return False
    logger.info(
        "WebSocket gossip subscriber connected: topic=%s chain=%s client=%s",
        state.topic,
        state.chain_id,
        state.client_ip,
    )

    # If this is a restricted topic, require authentication before any publish.
    if settings.gossip_auth_enabled and is_restricted_topic(state.topic):
        issued = create_challenge(state.client_ip)
        if issued is None:
            _auth_rejected("challenge_rate_limited", state.chain_id, state.topic)
            await _gossip_ws_send_json(state.websocket, {"error": "Challenge rate limited"})
            await _gossip_ws_close(state.websocket, code=1008)
            return False
        state.challenge, state.challenge_ts = issued
        await _gossip_ws_send_json(
            state.websocket,
            {"type": "auth_challenge", "challenge": state.challenge, "timestamp": state.challenge_ts},
        )
    return True


async def _gossip_ensure_subscription(state: _GossipConnState) -> None:
    if state.subscription is None:
        state.subscription = await state.broker.subscribe(state.topic, max_queue_size=100)
        state.subscription_ready.set()  # noqa: unawaited-async — asyncio.Event.set is synchronous


async def _gossip_forward_one_message(state: _GossipConnState, sub: TopicSubscription, message: Any) -> bool:
    """Forward one broker message to the client; False = send failed, stop."""
    # #1308: receiver/server-side record keyed by the same
    # deterministic event id the publisher computed — this is
    # the echo the client's ack wait resolves on, so its
    # presence/absence is what separates "delivered but
    # unacked" from "never reached the server".
    event_id = _message_id(state.topic, message)
    try:
        await _gossip_ws_send_json(state.websocket, message)
    except Exception as send_exc:
        gossip_ws_echo_forward_failed_total.labels(topic_class=bounded_topic_label(state.topic)).inc()
        gossip_event(
            "echo_forward_failed",
            peer=state.client_ip,
            topic=state.topic,
            event_id=event_id,
            error=str(send_exc)[:120],
            _level="warning",
        )
        return False
    gossip_ws_echo_forward_total.labels(topic_class=bounded_topic_label(state.topic)).inc()
    queue_depth = _subscription_queue_depth(sub)
    if queue_depth is not None:
        gossip_ws_subscriber_queue_depth.labels(topic_class=bounded_topic_label(state.topic)).set(  # noqa: unawaited-async — prometheus Gauge.set is synchronous
            float(queue_depth)
        )
    gossip_event(
        "echo_forward",
        peer=state.client_ip,
        topic=state.topic,
        event_id=event_id,
        queue_depth=queue_depth,
    )
    return True


async def _gossip_forward_broker_to_client(state: _GossipConnState) -> None:
    await state.subscription_ready.wait()
    sub = state.subscription
    if sub is None:
        return
    try:
        async for message in sub:
            if not await _gossip_forward_one_message(state, sub, message):
                break
    except Exception as e:
        logger.warning("Error forwarding broker message for %s: %s", state.topic, e)


async def _gossip_send_ping(state: _GossipConnState) -> bool:
    """Idle-timeout ping; False when the socket is already dead."""
    try:
        await _gossip_ws_send_json(state.websocket, {"type": "ping", "timestamp": time.time()})
    except Exception as e:  # noqa: BLE001 - dead socket ends the receive loop
        logger.debug("gossip ping send failed: %s", type(e).__name__)
        return False
    return True


async def _gossip_rate_limited(state: _GossipConnState, reason: str, reject_reason: str) -> None:
    """Shared per-class + per-IP-total message-rate rejection path."""
    gossip_rate_limited_total.labels(reason=reason).inc()
    _note_rejection(state.chain_id, state.topic, reject_reason)
    # #1308: rate-limited publishes never reach json.loads, so
    # no event id is computable — still worth an INFO record:
    # a missing ack with a rate_limited line is the answer.
    gossip_event(
        "rate_limited",
        peer=state.client_ip,
        topic=state.topic,
        reason=reason,
        _level="info",
    )
    await _gossip_ws_send_json(state.websocket, {"error": "Rate limit exceeded"})


async def _gossip_handle_peer_auth(state: _GossipConnState, data: dict[str, Any]) -> None:
    # Peer-key auth for public-topic publish (#1874). The key
    # travels in-band, never in the URL — uvicorn access logs
    # record the query string. Accepted set matches /subscribe/ws:
    # own RPC key, configured peer key, or live issued join key.
    if not settings.gossip_auth_enabled:
        state.peer_authorized = True
        await _gossip_ws_send_json(state.websocket, {"type": "peer_auth_ok", "note": "auth not required"})
        return
    peer_key = data.get("api_key")
    if isinstance(peer_key, str) and rpc_peer_key_accepted(peer_key):
        state.peer_authorized = True
        await _gossip_ws_send_json(state.websocket, {"type": "peer_auth_ok"})
    else:
        _note_rejection(state.chain_id, state.topic, "peer_auth_invalid")
        await _gossip_ws_send_json(state.websocket, {"type": "peer_auth_error", "error": "Invalid peer key"})


async def _gossip_handle_auth_response(state: _GossipConnState, data: dict[str, Any]) -> bool:
    """Validator challenge/response; False = socket closed, stop the loop."""
    if not settings.gossip_auth_enabled:
        await _gossip_ws_send_json(state.websocket, {"type": "auth_ok", "note": "auth not required"})
        return True
    claimed = data.get("address", "")
    signature = data.get("signature", "")
    client_challenge = data.get("challenge", "")
    client_ts = data.get("timestamp", 0.0)
    if not is_validator(claimed):
        _auth_rejected("not_validator", state.chain_id, state.topic)
        await _gossip_ws_send_json(state.websocket, {"error": "Not a validator"})
        await _gossip_ws_close(state.websocket, code=1008)
        return False
    if client_challenge != state.challenge:
        _auth_rejected("challenge_mismatch", state.chain_id, state.topic)
        await _gossip_ws_send_json(state.websocket, {"error": "Challenge mismatch"})
        await _gossip_ws_close(state.websocket, code=1008)
        return False
    if abs(time.time() - client_ts) > settings.gossip_auth_challenge_ttl:
        _auth_rejected("challenge_expired", state.chain_id, state.topic)
        await _gossip_ws_send_json(state.websocket, {"error": "Challenge expired"})
        await _gossip_ws_close(state.websocket, code=1008)
        return False
    if verify_challenge(
        client_challenge,
        claimed,
        client_ts,
        signature,
        channel_scope(state.topic, state.chain_id),
        legacy_scope=channel_scope(state.topic),
    ):
        if not state.authorized:
            gossip_authenticated_connections.labels(address=claimed).inc()
        state.authorized = True
        state.authorized_address = claimed
        gossip_auth_accepted_total.labels(address=claimed).inc()
        await _gossip_ws_send_json(state.websocket, {"type": "auth_ok", "address": claimed})
        # Deferred subscribe for restricted topics — the
        # broker feed only flows after validator auth.
        await _gossip_ensure_subscription(state)
        return True
    _auth_rejected("invalid_signature", state.chain_id, state.topic)
    await _gossip_ws_send_json(state.websocket, {"error": "Invalid signature"})
    await _gossip_ws_close(state.websocket, code=1008)
    return False


async def _gossip_publish_denied(
    state: _GossipConnState, data: dict[str, Any], reason: str, error: str, *, auth: bool
) -> bool:
    """Record + send + close a publish rejection; always returns False (stop)."""
    if auth:
        _auth_rejected(reason, state.chain_id, state.topic)
    else:
        _note_rejection(state.chain_id, state.topic, reason)
    gossip_event(
        "publish_rejected",
        peer=state.client_ip,
        topic=state.topic,
        reason=reason,
        event_id=_message_id(state.topic, data),
        _level="info",
    )
    await _gossip_ws_send_json(state.websocket, {"error": error})
    await _gossip_ws_close(state.websocket, code=1008)
    return False


async def _gossip_handle_publish(state: _GossipConnState, data: dict[str, Any]) -> bool:
    """Publish authorization gates, then broker.publish; False = socket closed."""
    topic = state.topic
    # Publishing path.
    if is_restricted_topic(topic) and not state.authorized:
        return await _gossip_publish_denied(
            state, data, "unauthorized_publish", "Validator authentication required", auth=True
        )
    if not is_public_topic(topic) and not state.authorized:
        return await _gossip_publish_denied(state, data, "unauthorized_topic", "Topic not authorized", auth=True)

    # #1874: public topics are subscribe-open but publish-gated —
    # a peer credential (or validator auth) is required so an
    # anonymous internet caller cannot inject forged tx/status/
    # mempool gossip. GOSSIP_PUBLIC_PUBLISH_REQUIRE_KEY=false is
    # the pre-#1874 escape hatch.
    if (
        is_public_topic(topic)
        and settings.gossip_auth_enabled
        and settings.gossip_public_publish_require_key
        and not state.authorized
        and not state.peer_authorized
    ):
        return await _gossip_publish_denied(
            state, data, "peer_key_required", "Peer key required to publish on public topics", auth=False
        )

    # #1308: server-side receive record — same deterministic
    # event id the publisher used, so a client-side ack timeout
    # can be matched against rx/broker/echo stages.
    event_id = _message_id(topic, data)
    gossip_ws_rx_publish_total.labels(topic_class=bounded_topic_label(topic)).inc()
    queue_depth = _subscription_queue_depth(state.subscription)
    if queue_depth is not None:
        gossip_ws_subscriber_queue_depth.labels(topic_class=bounded_topic_label(topic)).set(  # noqa: unawaited-async — prometheus Gauge.set is synchronous
            float(queue_depth)
        )
    gossip_event(
        "rx_publish",
        peer=state.client_ip,
        topic=topic,
        event_id=event_id,
        queue_depth=queue_depth,
        **_rx_publish_extra_fields(data),
    )
    try:
        await state.broker.publish(topic, data)
        gossip_messages_published_total.labels(topic=bounded_topic_label(topic)).inc()
    except Exception as e:  # noqa: BLE001 - one bad publish must not close the socket
        # A broker-side failure (e.g. an ACL-denied topic) loses
        # this message — but must not close the connection: the
        # same socket carries other topics and the receive path,
        # and tearing it down on one bad publish churns the whole
        # attestation transport.
        logger.warning("Broker publish failed for topic %s — message dropped: %s", topic, e)
        metrics_registry.increment("gossip_broker_publish_failed_total")
        gossip_event(
            "broker_publish_failed",
            peer=state.client_ip,
            topic=topic,
            event_id=event_id,
            error=str(e)[:120],
            _level="warning",
        )
    return True


async def _gossip_process_message(state: _GossipConnState, raw: str) -> bool:
    """Handle one inbound frame; False ends the receive loop (socket closed)."""
    if len(raw) > settings.gossip_max_message_size:
        gossip_oversized_message_total.inc()
        await _gossip_ws_send_json(state.websocket, {"error": "Message too large"})
        await _gossip_ws_close(state.websocket, code=1009)
        return False
    if not _gossip_msg_rate.is_allowed(_gossip_rate_key(state.client_ip, state.chain_id, state.topic)):
        await _gossip_rate_limited(state, "message_rate", "rate")
        return True
    if not _message_total_allowed(state.client_ip):
        await _gossip_rate_limited(state, "message_rate_total", "rate_total")
        return True

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await _gossip_ws_send_json(state.websocket, {"error": "Invalid JSON"})
        return True

    if data.get("type") == "peer_auth":
        await _gossip_handle_peer_auth(state, data)
        return True
    # Handle authentication handshake.
    if data.get("type") == "auth_response":
        return await _gossip_handle_auth_response(state, data)
    return await _gossip_handle_publish(state, data)


async def _gossip_forward_client_to_broker(state: _GossipConnState) -> None:
    while True:
        try:
            raw = await asyncio.wait_for(state.websocket.receive_text(), timeout=60.0)
        except asyncio.TimeoutError:
            if not await _gossip_send_ping(state):
                break
            continue
        except WebSocketDisconnect:
            break
        if not await _gossip_process_message(state, raw):
            break


async def _gossip_run_forwarders(state: _GossipConnState) -> None:
    """Run the two forwarder tasks to first completion, then tear down."""
    from asyncio import create_task, wait

    broker_task = create_task(_gossip_forward_broker_to_client(state))
    client_task = create_task(_gossip_forward_client_to_broker(state))
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
                logger.info("WebSocket gossip subscriber disconnected: topic=%s", state.topic)
            elif exc is not None:
                logger.error("WebSocket gossip error for topic %s: %s", state.topic, exc)
    except WebSocketDisconnect:
        logger.info("WebSocket gossip subscriber disconnected: topic=%s", state.topic)
    except Exception as e:
        logger.error("WebSocket gossip error for topic %s: %s", state.topic, e)
    finally:
        for task in (broker_task, client_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(broker_task, client_task, return_exceptions=True)
        if state.subscription is not None:
            state.subscription.close()  # noqa: unawaited-async — TopicSubscription.close() is synchronous (pre-existing bare call preserved)
        await _gossip_ws_close(state.websocket)


@router.websocket("/gossip/ws")
async def gossip_websocket(websocket: WebSocket) -> None:
    """Bidirectional WebSocket gossip with validator authentication.

    Clients connect with ``?topic=<topic>``. Publishing to validator-only
    topics (``blocks``, ``pbft``, ``consensus`` and any dotted sub-topic)
    requires a signed challenge/response using a key from ``VALIDATOR_SET``.
    Public topics (``transactions``, ``status``, ``mempool`` and any dotted
    sub-topic) may be subscribed without authentication, but publishing
    requires a peer credential (#1874): a ``{"type": "peer_auth",
    "api_key": ...}`` frame carrying this node's RPC key, a configured
    ``BLOCKCHAIN_RPC_API_KEY_PEERS`` key, or a live issued join key — the
    same credential set ``/subscribe/ws`` and the lease routes accept.
    ``GOSSIP_PUBLIC_PUBLISH_REQUIRE_KEY=false`` restores the pre-#1874
    open-publish behaviour; per-IP connection caps and per-topic-class
    message budgets apply either way.

    The server bridges messages into the node's ``gossip_broker`` so remote
    validators can publish and subscribe to gossip channels over the existing
    ``/rpc`` WSS path.
    """
    topic = websocket.query_params.get("topic")
    if not topic:
        await _gossip_ws_close(websocket, code=1008)
        return

    admitted = await _gossip_admit(websocket, topic)
    if admitted is None:
        return
    chain_id, broker = admitted

    client_ip = _gossip_client_ip(websocket)
    conn_key = await _gossip_acquire_slot(websocket, client_ip, chain_id, topic)
    if conn_key is None:
        return
    gossip_open_connections.inc()
    gossip_ws_open_connections.labels(chain=_chain_label(chain_id)).inc()

    state = _GossipConnState(websocket, topic, chain_id, client_ip, broker)
    try:
        if not await _gossip_accept_and_challenge(state):
            return

        # Restricted topics gate the broker subscription itself on validator
        # auth, not just publish — the relay /ws transport already requires
        # auth for the same channels, and an anonymous peer reading the
        # blocks/pbft/consensus feed is a transport disagreement (#1947 F5).
        # The subscribe is deferred until auth_ok for those topics.
        if not (settings.gossip_auth_enabled and is_restricted_topic(topic)):
            await _gossip_ensure_subscription(state)

        await _gossip_run_forwarders(state)
    finally:
        _release_ip_connection(conn_key)
        gossip_open_connections.dec()
        gossip_ws_open_connections.labels(chain=_chain_label(chain_id)).dec()
        if state.authorized_address:
            gossip_authenticated_connections.labels(address=state.authorized_address).dec()


class _SubscribeHandshake:
    """Outcome of the /subscribe/ws accept + frame + lease handshake.

    ``node_id``/``chain_id``/``transport`` are bound as soon as the frame
    parses — including on rejection paths — so the handler's ``finally``
    block observes the same values the inline code left behind. A plain
    class for the same fresh-worker-module reason as ``_GossipConnState``.
    """

    def __init__(self) -> None:
        self.node_id: Any = None
        self.chain_id: Any = ""
        self.transport: Any = None
        self.accepted = False


async def _subscribe_authorize(websocket: WebSocket, node_id: Any, chain_id: Any, data: dict[str, Any]) -> bool:
    """Peer-key + node_id binding + lease validation; False = rejected (closed)."""
    # #1702: the lease check below proves a lease EXISTS for the claimed
    # node_id — it says nothing about who is asking, and /rpc/subscribers
    # is public, so any valid node_id could be claimed anonymously. Require
    # the same peer-key credential the REST lease routes enforce, with the
    # same issued-key node_id binding.
    api_key = data.get("api_key")
    if not isinstance(api_key, str) or not rpc_peer_key_accepted(api_key):
        logger.warning("Subscribe websocket rejected: missing or invalid peer key (node_id=%s)", node_id)
        await _gossip_ws_send_json(websocket, {"error": "Valid peer key required (api_key)"})
        await _gossip_ws_close(websocket, code=1008)
        return False
    # Same classification as the REST lease routes (#1994): fleet keys
    # are unbound; any other authenticated key must resolve to an active
    # issued scope — a revoked-or-unresolvable scope fails closed rather
    # than silently skipping the node_id binding.
    if not rpc_fleet_key_accepted(api_key):
        scope = peer_keys.peer_key_node_scope(api_key)
        if scope is None or scope != node_id:
            await _gossip_ws_send_json(websocket, {"error": "Peer key is bound to a different node_id"})
            await _gossip_ws_close(websocket, code=1008)
            return False
    try:
        expiry = await lease_tracker.get_lease_expiry(node_id, chain_id)

        if expiry <= time.time():
            await _gossip_ws_send_json(
                websocket, {"error": "No valid lease found. Register subscription first via POST /rpc/subscribe"}
            )
            await _gossip_ws_close(websocket, code=1008)
            return False
    except Exception as e:
        logger.error("Failed to validate lease for %s: %s", node_id, e)
        await _gossip_ws_send_json(websocket, {"error": "Failed to validate lease"})
        await _gossip_ws_close(websocket, code=1011)
        return False
    return True


async def _subscribe_handshake(websocket: WebSocket) -> _SubscribeHandshake:
    """Accept the socket and validate the subscription frame + lease.

    Every rejection path closes the socket and returns the partially-filled
    result with ``accepted=False`` — the caller returns and the ``finally``
    block still sees the parsed ``node_id``/``chain_id``.
    """
    result = _SubscribeHandshake()
    try:
        await asyncio.wait_for(websocket.accept(), timeout=_GOSSIP_WS_OP_TIMEOUT)
    except TimeoutError:
        await _gossip_ws_close(websocket, code=1011)
        return result
    # The handshake frame is the only inbound message this endpoint reads,
    # but it was unbounded: a client that never sends (or trickles one)
    # held the connection — and its slot in _active_subscribers bookkeeping
    # — forever, and an oversized frame was buffered whole. Same bounds as
    # the gossip ws path: a receive timeout plus the gossip message cap.
    try:
        message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await _gossip_ws_close(websocket, code=1008)
        return result
    if len(message) > settings.gossip_max_message_size:
        await _gossip_ws_close(websocket, code=1009)
        return result
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        await _gossip_ws_send_json(websocket, {"error": "Invalid JSON"})
        await _gossip_ws_close(websocket, code=1008)
        return result
    if not isinstance(data, dict):
        await _gossip_ws_send_json(websocket, {"error": "Subscription message must be a JSON object"})
        await _gossip_ws_close(websocket, code=1008)
        return result
    result.node_id = data.get("node_id")
    result.chain_id = data.get("chain_id", settings.chain_id)
    result.transport = data.get("transport", "websocket")
    if not result.node_id:
        await _gossip_ws_send_json(websocket, {"error": "node_id is required"})
        await _gossip_ws_close(websocket, code=1008)
        return result
    if not await _subscribe_authorize(websocket, result.node_id, result.chain_id, data):
        return result
    result.accepted = True
    return result


async def _subscribe_send_blocks(websocket: WebSocket, node_id: str, block_subscription: TopicSubscription) -> None:
    """Send blocks to subscriber."""
    try:
        async for block_data in block_subscription:
            if isinstance(block_data, str):
                block_data = json.loads(block_data)
            # Bounded send (#1587): a peer that stops reading must
            # not wedge this task — same _GOSSIP_WS_OP_TIMEOUT the
            # gossip ws path got in #1165.
            await _gossip_ws_send_json(websocket, block_data)
            logger.debug("Sent block to %s", node_id)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for %s", node_id)
    except Exception as e:
        logger.error("Error sending block to %s: %s", node_id, e)


async def _subscribe_heartbeat(websocket: WebSocket, node_id: str, chain_id: str) -> None:
    """Send periodic pings to keep connection alive."""
    try:
        while True:
            await asyncio.sleep(20)
            # #1587: the lease was only validated at handshake — a
            # connection that outlives its lease kept receiving
            # block pushes forever. Revalidate each heartbeat; a
            # lapsed lease closes the stream. A lease_tracker error
            # is transient and must not drop live subscribers.
            try:
                lease_expiry = await lease_tracker.get_lease_expiry(node_id, chain_id)
            except Exception as e:
                logger.warning("Lease revalidation failed for %s: %s", node_id, e)
                lease_expiry = time.time() + 1
            if lease_expiry <= time.time():
                logger.info("Lease expired for %s; closing subscribe ws", node_id)
                await _gossip_ws_close(websocket, code=1008)
                return
            await _gossip_ws_send_json(websocket, {"type": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:  # expected disconnect
        pass
    # intentional silent cleanup
    except Exception as e:  # noqa: BLE001,S110 - receive-loop teardown  # nosec B110
        logger.debug("gossip receive loop cleanup failed: %s", type(e).__name__)


async def _subscribe_run_forwarders(
    websocket: WebSocket,
    node_id: str,
    chain_id: str,
    block_subscription: TopicSubscription,
) -> None:
    from asyncio import create_task, wait

    block_task = create_task(_subscribe_send_blocks(websocket, node_id, block_subscription))
    heartbeat_task = create_task(_subscribe_heartbeat(websocket, node_id, chain_id))
    done, pending = await wait([block_task, heartbeat_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@router.websocket("/subscribe/ws")
async def subscription_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for follower nodes to subscribe to block pushes.

    Protocol:
    1. Client connects and sends subscription message: {"node_id": "...", "chain_id": "...", "transport": "websocket"}
    2. Server validates the subscriber has a valid lease
    3. Server subscribes to block topic and pushes new blocks to client
    4. Server sends ping every 20s, expects pong response
    """
    # #1587: per-source-IP connection cap, taken BEFORE accept so a refused
    # client never gets a socket (or a broker subscription slot).
    client_ip = _gossip_client_ip(websocket)
    if not _acquire_subscribe_ip_slot(client_ip):
        logger.warning("Subscribe websocket connection limit for %s", client_ip)
        await _gossip_ws_close(websocket, code=1008)
        return
    # Bound before the handshake so the finally block can look up the entry
    # even when the client disconnects before sending its subscription message.
    node_id: Any = None
    chain_id: Any = ""
    try:
        handshake = await _subscribe_handshake(websocket)
        node_id = handshake.node_id
        chain_id = handshake.chain_id
        if not handshake.accepted:
            return
        transport = handshake.transport
        _active_subscribers[node_id, chain_id] = websocket
        logger.info("WebSocket subscriber connected: %s (chain=%s, transport=%s)", node_id, chain_id, transport)
        await _gossip_ws_send_json(
            websocket, {"status": "subscribed", "node_id": node_id, "chain_id": chain_id, "transport": transport}
        )
        topic = f"blocks.{chain_id}"
        broker = _broker_for_chain(chain_id)
        if broker is None:
            await _gossip_ws_send_json(websocket, {"error": "Unsupported chain"})
            await _gossip_ws_close(websocket, code=1008)
            return
        block_subscription = await broker.subscribe(topic, max_queue_size=100)
        await _subscribe_run_forwarders(websocket, node_id, chain_id, block_subscription)
    except WebSocketDisconnect:
        logger.info("WebSocket subscriber disconnected: %s", node_id)
    except Exception as e:
        logger.error("WebSocket error for %s: %s", node_id, e)
    finally:
        _release_subscribe_ip_slot(client_ip)
        if node_id and (node_id, chain_id) in _active_subscribers:
            del _active_subscribers[node_id, chain_id]
        try:
            await _gossip_ws_close(websocket)
        except Exception as e:  # noqa: BLE001,S110 - subscriber cleanup close is best-effort  # nosec
            logger.debug("gossip websocket cleanup close failed: %s", type(e).__name__)
        logger.info("WebSocket subscriber cleanup complete: %s", node_id)
