from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from ..config import settings
from ..metrics import metrics_registry
from ..network.compression import decode_payload, encode_payload
from .gossip_auth import gossip_topic_class


# Topics this node itself uses, as ``<prefix>.<chain_id>`` over its served
# chains (plus the bare roots). Everything else is collapsed to a class bucket
# before it reaches a metric name or label (#1250).
_OWN_TOPIC_ROOTS = ("blocks", "pbft", "consensus", "transactions", "status", "mempool")
_OWN_TOPIC_PREFIXES = (
    "blocks",
    "transactions",
    "status",
    "mempool",
    "pbft.pre_prepare",
    "pbft.prepare",
    "pbft.commit",
    "consensus.attest_request",
    "consensus.attest_response",
)


def _known_chain_ids() -> frozenset[str]:
    ids = set(settings.served_chain_ids())
    ids.update(settings.gossip_backend_map())
    if settings.chain_id:
        ids.add(settings.chain_id)
    return frozenset(ids)


def bounded_topic_label(topic: str) -> str:
    """Return a metric-safe, bounded label for a gossip topic (#1250).

    ``gossip_publications_topic_<t>``, ``gossip_queue_size_<t>``,
    ``gossip_subscribers_topic_<t>`` and the ``topic`` label of
    ``blockchain_gossip_messages_published_total`` used the raw topic string,
    which a remote caller chooses: ``is_public_topic`` admits any dotted
    subtopic of ``status``/``transactions``/``mempool``, so every new
    subtopic minted new series in the process-lifetime registry (never
    removed) and in the ``/metrics`` output. Only the node's own topics keep
    their exact name (alerts such as ``gossip_mesh_publications_topic_blocks_bc_2``
    depend on it): a bare root, or ``<known prefix>.<served chain id>``.
    Everything else collapses to ``other.<class>`` with
    ``class in public|blocks|pbft|consensus|other``, so the keyspace is
    bounded by (own topics x served chains) + 5.
    """
    if topic in _OWN_TOPIC_ROOTS:
        return topic
    prefix, sep, chain = topic.rpartition(".")
    if sep and prefix in _OWN_TOPIC_PREFIXES and chain in _known_chain_ids():
        return topic
    return f"other.{gossip_topic_class(topic)}"


def _increment_publication(metric_prefix: str, topic: str) -> None:
    metrics_registry.increment(f"{metric_prefix}_total")
    metrics_registry.increment(f"{metric_prefix}_topic_{bounded_topic_label(topic)}")


def _set_queue_gauge(topic: str, size: int) -> None:
    metrics_registry.set_gauge(f"gossip_queue_size_{bounded_topic_label(topic)}", float(size))


# Subscriber-gauge labels emitted so far, so a bucket whose last topic is gone
# is zeroed instead of keeping a stale value. Bounded like the labels.
_subscriber_labels: set[str] = set()


def _update_subscriber_metrics(topics: dict[str, list[asyncio.Queue[Any]]]) -> None:
    counts: dict[str, int] = {}
    for topic, queues in topics.items():
        label = bounded_topic_label(topic)
        counts[label] = counts.get(label, 0) + len(queues)
    for label in _subscriber_labels - counts.keys():
        metrics_registry.set_gauge(f"gossip_subscribers_topic_{label}", 0.0)
    for label, count in counts.items():
        metrics_registry.set_gauge(f"gossip_subscribers_topic_{label}", float(count))
    _subscriber_labels.update(counts)
    total = sum(len(queues) for queues in topics.values())
    metrics_registry.set_gauge("gossip_subscribers_total", float(total))


def _clear_topic_metrics(topic: str) -> None:
    label = bounded_topic_label(topic)
    # A collapsed bucket is shared by many topics; the caller's following
    # ``_update_subscriber_metrics`` recomputes it, so only an own topic
    # (exclusively this label) is zeroed here.
    if not label.startswith("other."):
        metrics_registry.set_gauge(f"gossip_subscribers_topic_{label}", 0.0)
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
