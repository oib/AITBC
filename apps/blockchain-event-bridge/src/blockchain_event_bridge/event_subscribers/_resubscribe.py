"""Gossip subscription recovery helpers (#1650)."""

from __future__ import annotations

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def close_subscription(subscription: Any) -> None:
    if subscription is None:
        return
    try:
        subscription.close()
    except Exception as exc:
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
