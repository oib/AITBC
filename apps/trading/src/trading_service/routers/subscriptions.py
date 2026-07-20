"""Offer subscription, heartbeat, search, and WebSocket endpoints."""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.trading.subscription_types import OfferEvent, OfferNotification, OfferSubscription

from ..config import settings
from ..state import (
    _synced_offer_to_dict,
    get_notification_service,
    get_search_service,
    get_subscription_service,
)

router = APIRouter(tags=["subscriptions"])
logger = get_logger(__name__)


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
    try:
        expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id)
    except Exception as e:
        logger.warning("Lease registration failed for %s: %s — using computed expiry", node_id, e)
        expiry = time.time() + lease_duration
    return {"node_id": node_id, "chain_id": chain_id, "expiry": expiry, "lease_duration": lease_duration}


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
    try:
        expiry = await svc.renew_lease(node_id=node_id)
        if expiry == 0.0:
            # Lease not found — re-register so the client can continue
            expiry = await svc.register_lease(node_id=node_id, chain_id=chain_id)
    except Exception as e:
        logger.warning("Lease renewal failed for %s: %s — using computed expiry", node_id, e)
        expiry = time.time() + lease_duration
    return {"node_id": node_id, "chain_id": chain_id, "expiry": expiry, "renewed": True}


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
    subscriber_id: str | None = None
    sub_svc = get_subscription_service()
    notif_svc = get_notification_service()

    try:
        # Receive first message with subscription config
        message = await websocket.receive_text()
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            await websocket.close(code=1008)
            return

        node_id = data.get("node_id", "")
        chain_id = data.get("chain_id", settings.default_chain_id)
        filters = data.get("filters", {})

        if not node_id:
            await websocket.send_json({"error": "node_id is required"})
            await websocket.close(code=1008)
            return

        subscriber_id = f"{node_id}:{chain_id}"

        # v0.10.1 §B19: Register a lease for this subscriber
        lease_expiry: float = 0.0
        try:
            lease_expiry = await sub_svc.register_lease(node_id=node_id, chain_id=chain_id)
        except Exception as e:
            logger.warning("WebSocket lease registration failed for %s: %s", node_id, e)

        # Build subscription from filters
        subscription = OfferSubscription(
            chain_id=filters.get("chain_id", chain_id),
            service_type=filters.get("service_type"),
            min_price=filters.get("min_price"),
            max_price=filters.get("max_price"),
            region=filters.get("region"),
            gpu_model=filters.get("gpu_model"),
            debounce_ms=settings.offer_subscription_debounce_ms,
        )

        # Notification callback — sends batch to this WebSocket
        async def _notify(notification: OfferNotification) -> None:
            try:
                await websocket.send_json(notification.to_dict())
            except Exception:
                pass

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
            }
        )

        # Event forwarding: inject events into notification service
        async def _forward_to_notifications(event: OfferEvent) -> None:
            await notif_svc.process_event(event)

        sub_svc._on_event = _forward_to_notifications  # noqa: SLF001

        # Heartbeat + receive loop
        async def _heartbeat() -> None:
            try:
                while True:
                    await asyncio.sleep(settings.offer_subscription_heartbeat_seconds)
                    # v0.10.1 §B19: Renew lease on each heartbeat
                    try:
                        await sub_svc.renew_lease(node_id=node_id)
                    except Exception:
                        pass
                    await websocket.send_json({"type": "ping", "timestamp": time.time()})
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        async def _receive_loop() -> None:
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
                            except Exception:
                                pass  # tolerate lease-check errors
                            continue
                    except json.JSONDecodeError:
                        continue
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        heartbeat_task = create_task_with_logging(_heartbeat(), name="trading_offer_heartbeat")
        receive_task = create_task_with_logging(_receive_loop(), name="trading_offer_receive")
        done, pending = await asyncio.wait([heartbeat_task, receive_task], return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info("Offer WebSocket subscriber disconnected: %s", subscriber_id)
    except Exception as e:
        logger.error("Offer WebSocket error for %s: %s", subscriber_id, e)
    finally:
        if subscriber_id:
            await notif_svc.unregister_subscriber(subscriber_id)
            # v0.10.1 §B19: Revoke lease on disconnect
            try:
                parts = subscriber_id.split(":", 1)
                if len(parts) == 2:
                    await sub_svc.revoke_lease(parts[0])
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/v1/trading/offers/subscription-status")
async def get_subscription_status():
    """Get per-chain subscription health status.

    Returns: chain_id, status (subscribed/reconnecting/polling_fallback),
    last_event, event_count for each chain with an active subscription.
    """
    svc = get_subscription_service()
    return svc.get_chain_status()


@router.get("/v1/trading/offers/search")
async def search_offers(
    q: str = "",
    chain_id: str | None = None,
    service_type: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 100,
):
    """Search offers via the optional search index (B7).

    Falls back to in-memory search when the external index is unavailable.
    """
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
