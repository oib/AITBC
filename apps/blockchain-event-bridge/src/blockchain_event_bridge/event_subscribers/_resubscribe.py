"""Gossip subscription recovery helpers (#1650)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GossipReadOutcome:
    kind: Literal["message", "retry", "cancelled"]
    subscription: Any
    message: dict[str, Any] | None = None


def close_subscription(subscription: Any) -> None:
    if subscription is None:
        return
    try:
        subscription.close()
    except Exception as exc:  # noqa: BLE001 — subscription close containment
        logger.debug("Ignoring error while closing gossip subscription: %s", exc)


async def resubscribe(
    broker: Any,
    topic: str,
    subscription: Any,
    *,
    max_queue_size: int = 100,
) -> Any:
    """Drop a stale subscription handle and open a fresh one."""
    close_subscription(subscription)
    logger.warning("Resubscribing to gossip topic %s", topic)
    return await broker.subscribe(topic, max_queue_size=max_queue_size)


async def read_gossip_with_recovery(
    broker: Any,
    topic: str,
    subscription: Any,
    *,
    label: str,
    max_queue_size: int = 100,
) -> GossipReadOutcome:
    """Read one gossip message, resubscribing when the handle is dead (#1650)."""
    try:
        if subscription is None:
            raise RuntimeError(f"{label} subscription not initialized")
        message = await subscription.get()
        return GossipReadOutcome("message", subscription, message)
    except asyncio.CancelledError:
        logger.info("%s event subscriber cancelled", label)
        return GossipReadOutcome("cancelled", subscription)
    except Exception as exc:
        logger.error("%s subscription read failed: %s", label, exc, exc_info=True)
        if broker is not None and topic:
            try:
                subscription = await resubscribe(broker, topic, subscription, max_queue_size=max_queue_size)
            except Exception as sub_err:
                logger.error("%s subscription resubscribe failed: %s", label, sub_err, exc_info=True)
        await asyncio.sleep(1)
        return GossipReadOutcome("retry", subscription)
