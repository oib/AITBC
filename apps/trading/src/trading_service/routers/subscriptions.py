"""Offer subscription, heartbeat, search, and WebSocket endpoints."""

from decimal import Decimal, InvalidOperation
import asyncio
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import anyio
from websockets.exceptions import ConnectionClosed

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.trading.subscription_types import OfferNotification, OfferSubscription

from ..config import settings
from ..services.lease_tracker import hash_lease_token
from ..state import (
    _synced_offer_to_dict,
    get_notification_service,
    get_search_service,
    get_subscription_service,
)

router = APIRouter(tags=["subscriptions"])
logger = get_logger(__name__)

# redis is an optional dependency (lazy-imported inside the lease/gossip
# services); fold its error base into the ops tuple only when importable.
try:
    from redis.exceptions import RedisError as _RedisError

    _REDIS_ERRORS: tuple[type[BaseException], ...] = (_RedisError,)
except ImportError:
    _REDIS_ERRORS = ()

# Expected failure surface for the lease/WebSocket fallbacks below: Redis
# transport errors via the lease tracker, WebSocket send/receive failures,
# JSON/decode and data-shape errors. RuntimeError covers abort-style raises;
# genuine BaseExceptions (incl. asyncio.CancelledError and
# WebSocketDisconnect, handled separately) still propagate (#1862).
_OPS_ERRORS = (
    OSError,
    ValueError,
    InvalidOperation,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    *_REDIS_ERRORS,
    anyio.EndOfStream,
    anyio.BrokenResourceError,
    anyio.ClosedResourceError,
    ConnectionClosed,
)

# #1608: offer price filters are Decimal-compared against offer prices. Bound
# them to finite, non-negative values within the same magnitude cap the
# exchange env-decimal path uses so NaN/negative/huge filters cannot reach
# the comparisons (or serialize into subscription state) unchecked.
_MAX_PRICE_FILTER = Decimal("1000000000000000")


def _price_filter(value: Any, name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        bound = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a decimal") from exc
    if not bound.is_finite() or bound < 0 or bound > _MAX_PRICE_FILTER:
        raise ValueError(f"{name} must be a finite price between 0 and {_MAX_PRICE_FILTER}")
    return bound


def _validated_price_filters(filters: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    min_price = _price_filter(filters.get("min_price"), "min_price")
    max_price = _price_filter(filters.get("max_price"), "max_price")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("min_price must not exceed max_price")
    return min_price, max_price


# Active WebSocket connections per node_id. Subscription leases are keyed
# by node_id and shared by all of a node's connections, so the lease is
# revoked only when the node's last connection closes.
_ws_connections_by_node: dict[str, int] = {}

# #3028: TRADING_API_KEY is a single shared service key, so node_id in the
# request body/first WS frame is self-asserted. Leases therefore carry a
# bearer token: subscribe issues a fresh ``lease_token`` (only its SHA-256
# hash is stored on the lease), and heartbeat/WebSocket subscribe for an
# already-active lease must present it. This binds lease mutation to the
# lease holder instead of to the shared key — a key holder can still open
# subscriptions for fresh node_ids (the feed is not tenant-scoped), but
# cannot squat, renew, or stream as another node's node_id.
_LEASE_TOKEN_BYTES = 32


def _new_lease_token() -> str:
    return secrets.token_urlsafe(_LEASE_TOKEN_BYTES)


def _lease_token_ok(presented: Any, stored_hash: str) -> bool:
    """Constant-time check of a presented bearer token against the stored hash."""
    return isinstance(presented, str) and bool(presented) and hmac.compare_digest(hash_lease_token(presented), stored_hash)


async def _lease_token_state_or_503(svc: Any, node_id: str) -> tuple[bool, str | None] | JSONResponse:
    """Read ``(active, token_hash)`` for ``node_id``, failing closed."""
    try:
        return await svc.lease_token_state(node_id)
    except _OPS_ERRORS as e:
        logger.warning("Lease token state read failed for %s: %s", node_id, e)
        return JSONResponse(status_code=503, content={"error": "lease store unavailable"})


@router.post("/v1/trading/offers/subscribe")
async def subscribe_to_offers(request: dict[str, Any]):
    """Register an offer subscription and obtain a lease.

    Mirrors the blockchain-node ``POST /rpc/subscribe`` pattern.
    Returns a lease expiry timestamp that the client uses to track
    when to renew via the heartbeat endpoint.

    v0.10.1 §B19: Uses the Redis-backed :class:`OfferLeaseTracker` for
    real lease management.  Falls back to a computed expiry when Redis
    is unavailable so the endpoint always returns a valid response.
    """
    node_id = request.get("node_id", "")
    chain_id = request.get("chain_id", settings.default_chain_id)
    if not node_id:
        return JSONResponse(status_code=400, content={"error": "node_id is required"})

    svc = get_subscription_service()
    lease_duration = settings.offer_subscription_heartbeat_seconds * 3
    state = await _lease_token_state_or_503(svc, node_id)
    if isinstance(state, JSONResponse):
        return state
    active, stored_hash = state
    presented_token = request.get("lease_token")
    lease_token_out: str | None = None
    if active:
        # An active lease may only be renewed by its bearer-token holder.
        # Leases issued before token binding (stored_hash None) are refused
        # until they expire and are re-issued — the window is one lease TTL.
        if stored_hash is None or not _lease_token_ok(presented_token, stored_hash):
            return JSONResponse(
                status_code=403,
                content={"error": "lease_token missing or does not match the active lease for node_id"},
            )
        try:
            expiry = await svc.renew_lease(node_id=node_id)
            if expiry == 0.0:
                # Lease vanished between the check and the renewal.
                lease_token_out = _new_lease_token()
                expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id, lease_token=lease_token_out)
        except _OPS_ERRORS as e:
            logger.warning("Lease renewal failed for %s: %s — using computed expiry", node_id, e)
            expiry = time.time() + lease_duration
    else:
        lease_token_out = _new_lease_token()
        try:
            expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id, lease_token=lease_token_out)
        except _OPS_ERRORS as e:
            logger.warning("Lease registration failed for %s: %s — using computed expiry", node_id, e)
            expiry = time.time() + lease_duration
    return {
        "node_id": node_id,
        "chain_id": chain_id,
        "expiry": expiry,
        "lease_duration": lease_duration,
        # Plaintext token is returned only when a new lease was issued;
        # it is null on renewal so the stored binding cannot be rotated
        # by re-subscribing with the same token.
        "lease_token": lease_token_out,
    }


@router.post("/v1/trading/offers/heartbeat")
async def offer_heartbeat(request: dict[str, Any]):
    """Renew an offer subscription lease.

    Mirrors the blockchain-node ``POST /rpc/heartbeat`` pattern.

    v0.10.1 §B19: Uses the Redis-backed :class:`OfferLeaseTracker` to
    renew the lease.  Falls back to a computed expiry when Redis is
    unavailable or the lease was not found.
    """
    node_id = request.get("node_id", "")
    chain_id = request.get("chain_id", settings.default_chain_id)
    if not node_id:
        return JSONResponse(status_code=400, content={"error": "node_id is required"})

    svc = get_subscription_service()
    lease_duration = settings.offer_subscription_heartbeat_seconds * 3
    state = await _lease_token_state_or_503(svc, node_id)
    if isinstance(state, JSONResponse):
        return state
    active, stored_hash = state
    presented_token = request.get("lease_token")
    lease_token_out: str | None = None
    if active:
        # #3028: renewing someone else's lease requires its bearer token.
        if stored_hash is None or not _lease_token_ok(presented_token, stored_hash):
            return JSONResponse(
                status_code=403,
                content={"error": "lease_token missing or does not match the active lease for node_id"},
            )
        try:
            expiry = await svc.renew_lease(node_id=node_id)
            if expiry == 0.0:
                # Lease vanished between the check and the renewal.
                lease_token_out = _new_lease_token()
                expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id, lease_token=lease_token_out)
        except _OPS_ERRORS as e:
            logger.warning("Lease renewal failed for %s: %s — using computed expiry", node_id, e)
            expiry = time.time() + lease_duration
    else:
        # No active lease — issue a fresh bound lease (same as subscribe).
        lease_token_out = _new_lease_token()
        try:
            expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id, lease_token=lease_token_out)
        except _OPS_ERRORS as e:
            logger.warning("Lease registration failed for %s: %s — using computed expiry", node_id, e)
            expiry = time.time() + lease_duration
    return {
        "node_id": node_id,
        "chain_id": chain_id,
        "expiry": expiry,
        "renewed": True,
        "lease_token": lease_token_out,
    }


async def _offer_ws_lease_gate(
    websocket: WebSocket, sub_svc: Any, node_id: str, presented_token: Any
) -> tuple[bool, str | None] | None:
    """#3028 lease-token gate for the WS handshake.

    Returns ``(active, stored_hash)`` when the socket may proceed, or
    ``None`` after sending an error + close. Runs before any subscriber
    refcount/lease side effects — a rejected socket must not decrement a
    sibling's count or revoke the real holder's lease in the caller's
    ``finally`` block.
    """
    try:
        active, stored_hash = await sub_svc.lease_token_state(node_id)
    except _OPS_ERRORS as e:
        logger.warning("WebSocket lease token check failed for %s: %s", node_id, e)
        await websocket.send_json({"error": "lease store unavailable"})
        await websocket.close(code=1011)
        return None
    if active and (stored_hash is None or not _lease_token_ok(presented_token, stored_hash)):
        await websocket.send_json({"error": "lease_token missing or does not match the active lease for node_id"})
        await websocket.close(code=1008)
        return None
    return active, stored_hash


async def _offer_ws_lease_ensure(sub_svc: Any, node_id: str, chain_id: str, active: bool) -> tuple[float, str | None]:
    """Renew an existing bound lease or issue a fresh one for ``node_id``.

    Returns ``(lease_expiry, lease_token_out)``; the plaintext token is
    only non-None when this socket issued the lease (fresh node_id or a
    lease that vanished mid-handshake).
    """
    lease_expiry: float = 0.0
    lease_token_out: str | None = None
    try:
        if active:
            lease_expiry = await sub_svc.renew_lease(node_id=node_id)
            if lease_expiry == 0.0:
                # Lease vanished between the gate and the renewal.
                lease_token_out = _new_lease_token()
                lease_expiry = await sub_svc.register_lease(node_id=node_id, chain_id=chain_id, lease_token=lease_token_out)
        else:
            lease_token_out = _new_lease_token()
            lease_expiry = await sub_svc.register_lease(node_id=node_id, chain_id=chain_id, lease_token=lease_token_out)
    except _OPS_ERRORS as e:
        logger.warning("WebSocket lease registration failed for %s: %s", node_id, e)
    return lease_expiry, lease_token_out


async def _offer_ws_setup(
    websocket: WebSocket,
    sub_svc: Any,
    notif_svc: Any,
    conn: dict[str, Any],
) -> bool:
    """Handshake phase of the offer WebSocket: receive config, validate,
    register lease/subscriber, start the chain feed and ack. Returns False
    after sending an error + close when the config is unusable. Progress is
    reported through ``conn`` so the caller's ``finally`` can clean up a
    partially-registered connection exactly as the inline version did."""
    # Receive first message with subscription config
    message = await websocket.receive_text()
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        await websocket.send_json({"error": "Invalid JSON"})
        await websocket.close(code=1008)
        return False

    node_id = data.get("node_id", "")
    chain_id = data.get("chain_id", settings.default_chain_id)
    filters = data.get("filters", {})
    conn["node_id"] = node_id

    if not node_id:
        await websocket.send_json({"error": "node_id is required"})
        await websocket.close(code=1008)
        return False
    if not isinstance(filters, dict):
        await websocket.send_json({"error": "filters must be an object"})
        await websocket.close(code=1008)
        return False
    try:
        min_price, max_price = _validated_price_filters(filters)
    except ValueError as exc:
        await websocket.send_json({"error": str(exc)})
        await websocket.close(code=1008)
        return False

    # #3028: node_id is self-asserted on a shared service key, so an
    # already-active lease may only be driven by its bearer-token holder.
    gate = await _offer_ws_lease_gate(websocket, sub_svc, node_id, data.get("lease_token"))
    if gate is None:
        return False
    active, _stored_hash = gate

    # Unique per connection: two sockets from the same node must not
    # overwrite each other's notification registration.
    subscriber_id = f"{node_id}:{chain_id}:{secrets.token_hex(4)}"
    conn["subscriber_id"] = subscriber_id
    _ws_connections_by_node[node_id] = _ws_connections_by_node.get(node_id, 0) + 1

    # v0.10.1 §B19: Register/renew a lease for this subscriber. A fresh
    # node_id gets a newly-issued bearer token returned in the ack; an
    # existing lease is only renewed (its token binding is unchanged).
    lease_expiry, lease_token_out = await _offer_ws_lease_ensure(sub_svc, node_id, chain_id, active)

    # Build subscription from filters
    subscription = OfferSubscription(
        chain_id=filters.get("chain_id", chain_id),
        service_type=filters.get("service_type"),
        min_price=min_price,
        max_price=max_price,
        region=filters.get("region"),
        gpu_model=filters.get("gpu_model"),
        debounce_ms=settings.offer_subscription_debounce_ms,
    )

    # Notification callback — sends batch to this WebSocket
    async def _notify(notification: OfferNotification) -> None:
        try:
            await websocket.send_json(notification.to_dict())
        except _OPS_ERRORS as e:
            logger.debug("Notification send failed for %s: %s", subscriber_id, e)

    await notif_svc.register_subscriber(subscriber_id, subscription, _notify)

    # Start chain subscription if not already running
    await sub_svc.start_chain(chain_id)

    await websocket.send_json(
        {
            "status": "subscribed",
            "node_id": node_id,
            "chain_id": chain_id,
            "filters": filters,
            "lease_expiry": lease_expiry,
            # Plaintext bearer token only when this socket issued the
            # lease; null when it joined an existing bound lease.
            "lease_token": lease_token_out,
        }
    )
    return True


async def _offer_ws_heartbeat(websocket: WebSocket, sub_svc: Any, node_id: str, subscriber_id: str) -> None:
    """Ping the socket every heartbeat interval and renew the node lease."""
    try:
        while True:
            await asyncio.sleep(settings.offer_subscription_heartbeat_seconds)
            # v0.10.1 §B19: Renew lease on each heartbeat
            try:
                await sub_svc.renew_lease(node_id=node_id)
            except _OPS_ERRORS as e:
                logger.debug("Lease renewal failed for %s: %s", node_id, e)
            await websocket.send_json({"type": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:
        pass
    except _OPS_ERRORS as e:
        logger.debug("Offer heartbeat task ended for %s: %s", subscriber_id, e)


async def _offer_ws_receive(websocket: WebSocket, sub_svc: Any, node_id: str, subscriber_id: str) -> None:
    """Read client frames; a ``pong`` triggers lease validation and an
    expired lease closes the socket."""
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                parsed = json.loads(msg)
                if parsed.get("type") == "pong":
                    # v0.10.1 §B19: Validate lease on WebSocket receive
                    try:
                        valid = await sub_svc.validate_lease(node_id=node_id)
                        if not valid:
                            logger.info("Lease invalid for %s — closing WebSocket", node_id)
                            await websocket.send_json({"error": "lease expired"})
                            await websocket.close(code=1008)
                            return
                    except _OPS_ERRORS as e:
                        # Tolerate lease-check errors; the lease TTL
                        # still bounds a dead subscription.
                        logger.debug("Lease validation failed for %s: %s", node_id, e)
                    continue
            except json.JSONDecodeError:
                continue
    except WebSocketDisconnect:
        pass
    except _OPS_ERRORS as e:
        logger.debug("Offer receive task ended for %s: %s", subscriber_id, e)


async def _offer_ws_run(websocket: WebSocket, sub_svc: Any, node_id: str, subscriber_id: str) -> None:
    """Run the heartbeat + receive tasks until the first completes, then
    cancel the survivor."""
    heartbeat_task = create_task_with_logging(
        _offer_ws_heartbeat(websocket, sub_svc, node_id, subscriber_id), name="trading_offer_heartbeat"
    )
    receive_task = create_task_with_logging(
        _offer_ws_receive(websocket, sub_svc, node_id, subscriber_id), name="trading_offer_receive"
    )
    done, pending = await asyncio.wait([heartbeat_task, receive_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@router.websocket("/v1/trading/offers/subscribe/ws")
async def offer_subscription_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time offer change streaming.

    Protocol:
    1. Client connects and sends first message with filters:
       {"node_id": "...", "chain_id": "...", "filters": {...}}
    2. Server registers the subscriber and starts streaming offer events
    3. Server sends ping every 20s to keep connection alive
    4. Events are debounced into batches via OfferNotificationService
    """
    await websocket.accept()
    conn: dict[str, Any] = {"node_id": "", "subscriber_id": None}
    sub_svc = get_subscription_service()
    notif_svc = get_notification_service()

    try:
        if not await _offer_ws_setup(websocket, sub_svc, notif_svc, conn):
            return
        await _offer_ws_run(websocket, sub_svc, conn["node_id"], conn["subscriber_id"])

    except WebSocketDisconnect:
        logger.info("Offer WebSocket subscriber disconnected: %s", conn["subscriber_id"])
    except _OPS_ERRORS as e:
        logger.error("Offer WebSocket error for %s: %s", conn["subscriber_id"], e)
    finally:
        subscriber_id = conn["subscriber_id"]
        node_id = conn["node_id"]
        if subscriber_id:
            # Use the bound node_id, not a re-parse of subscriber_id: a
            # node_id containing ':' would decrement/revoke a different
            # node's refcount (subscriber_id embeds chain_id and a token).
            try:
                await notif_svc.unregister_subscriber(subscriber_id)
            except _OPS_ERRORS as e:
                logger.debug("Unregistering subscriber %s failed: %s", subscriber_id, e)
            # v0.10.1 §B19: Revoke the node's lease only when its last
            # WebSocket connection closes — sibling connections share it.
            remaining = _ws_connections_by_node.get(node_id, 0) - 1
            if remaining > 0:
                _ws_connections_by_node[node_id] = remaining
            else:
                _ws_connections_by_node.pop(node_id, None)
                try:
                    await sub_svc.revoke_lease(node_id)
                except _OPS_ERRORS as e:
                    logger.debug("Lease revocation failed for %s: %s", node_id, e)
        try:
            await websocket.close()
        except _OPS_ERRORS as e:
            logger.debug("WebSocket close failed for %s: %s", subscriber_id, e)


@router.get("/v1/trading/offers/subscription-status")
def get_subscription_status():
    """Get per-chain subscription health status.

    Returns: chain_id, status (subscribed/reconnecting/polling_fallback),
    last_event, event_count for each chain with an active subscription.
    """
    svc = get_subscription_service()
    return svc.get_chain_status()


@router.get("/v1/trading/offers/search")
def search_offers(
    q: str = "",
    chain_id: str | None = None,
    service_type: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Search offers via the optional search index (B7).

    Falls back to in-memory search when the external index is unavailable.
    """
    # #1608: price bounds must be finite, non-negative, bounded, and ordered —
    # NaN/negative/huge/inverted filters are client errors, not 500s.
    try:
        min_price = _price_filter(min_price, "min_price")
        max_price = _price_filter(max_price, "max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("min_price must not exceed max_price")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    svc = get_search_service()
    results = svc.search(
        query=q,
        chain_id=chain_id,
        service_type=service_type,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
    )
    return [_synced_offer_to_dict(o) for o in results]
