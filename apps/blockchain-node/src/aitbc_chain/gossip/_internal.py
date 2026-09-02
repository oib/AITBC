from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from ..metrics import metrics_registry
from ..network.compression import decode_payload, encode_payload


def _increment_publication(metric_prefix: str, topic: str) -> None:
    metrics_registry.increment(f"{metric_prefix}_total")
    metrics_registry.increment(f"{metric_prefix}_topic_{topic}")


def _set_queue_gauge(topic: str, size: int) -> None:
    metrics_registry.set_gauge(f"gossip_queue_size_{topic}", float(size))


def _update_subscriber_metrics(topics: dict[str, list[asyncio.Queue[Any]]]) -> None:
    for topic, queues in topics.items():
        metrics_registry.set_gauge(f"gossip_subscribers_topic_{topic}", float(len(queues)))
    total = sum(len(queues) for queues in topics.values())
    metrics_registry.set_gauge("gossip_subscribers_total", float(total))


def _clear_topic_metrics(topic: str) -> None:
    metrics_registry.set_gauge(f"gossip_subscribers_topic_{topic}", 0.0)
    _set_queue_gauge(topic, 0)


def _message_id(topic: str, message: Any) -> str:
    """Deterministic identifier for a (topic, message) pair.

    Used for publish-side dedup in ``GossipBroker``, echo suppression in the
    websocket backend and receive-side dedup in the mesh backend, so the same
    message arriving over several links is recognised as one.

    * An explicit ``id`` field is always the identity.
    * ``hash`` is the identity only on ``blocks*`` topics, where it is the block
      hash. On other topics ``hash`` is a *reference* (attestation responses and
      PBFT messages all quote the block they vote on) and several distinct
      messages from different validators legitimately share it - keying on it
      there silently dropped all but the first attestation.
    * Everything else hashes its canonical JSON encoding.
    """
    if isinstance(message, dict):
        if "id" in message:
            return f"{topic}:{message['id']}"
        if "hash" in message and topic.split(".", 1)[0] == "blocks":
            return f"{topic}:{message['hash']}"
    payload = json.dumps(message, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{topic}:{digest}"


def _peer_name(url: str) -> str:
    """Short human-readable label for a peer URL (host[:port])."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc or url


def _encode_message(message: Any) -> Any:
    """Serialize a message for transport, compressing when enabled."""

    if isinstance(message, str | bytes | bytearray):
        return message
    return encode_payload(message)


def _decode_message(message: Any) -> Any:
    """Decode a transport payload, transparently decompressing if needed."""

    if isinstance(message, str | bytes | bytearray):
        return decode_payload(message)
    return message


def _encode_batch(messages: list[Any]) -> str:
    """Serialize a list of messages as a single compressed batch frame.

    The list is JSON-serialized then compressed with the ``GZ:`` prefix, so
    receivers can transparently detect and decompress it.
    """

    return encode_payload(messages)


def _decode_batch(data: Any) -> list[Any]:
    """Decode a transport payload into a list of messages.

    Handles three cases transparently for backward compatibility:

    * Batched messages (a JSON array after decompression) -> returned as-is.
    * Single messages (a JSON object after decompression) -> wrapped in a list.
    * Raw strings/bytes (no ``GZ:`` prefix) -> decoded and wrapped in a list.
    """

    decoded = decode_payload(data) if isinstance(data, str | bytes | bytearray) else data
    if isinstance(decoded, list):
        return decoded
    return [decoded]
