"""
Compression helpers for network payloads (gossip, Redis pub/sub, P2P TCP).

Wraps ``aitbc.network.compress_json`` / ``decompress_json`` with a magic-prefix
scheme so receivers can transparently detect and decompress payloads while
remaining backward-compatible with plain-JSON messages.

The prefix ``COMPRESSION_PREFIX`` (ASCII ``"GZ:"``) is prepended to the
base64-encoded compressed bytes.  This keeps the payload newline-free (safe
for the P2P readline protocol) and ASCII-safe (safe for Redis pub/sub).
"""

from __future__ import annotations

import base64
import json
from typing import Any

from aitbc.network import compress_json, decompress_json

# Magic prefix that marks a compressed payload.  Chosen so that it can never
# appear at the start of valid JSON (which always begins with ``{``, ``[``,
# ``"``, a digit, ``t``, ``f``, ``n``, or ``-``).
COMPRESSION_PREFIX = "GZ:"


def is_compression_enabled() -> bool:
    """Check whether network compression is enabled via configuration."""
    try:
        from ..config import settings

        return getattr(settings, "network_compression_enabled", True)
    except Exception:
        return True


def encode_payload(message: Any) -> str:
    """Serialize *message* to a transport-safe string.

    When compression is enabled the result is ``COMPRESSION_PREFIX`` followed by
    base64-encoded gzip-compressed JSON.  When disabled (or when *message* is
    already a string/bytes) the result is plain compact JSON.
    """
    if isinstance(message, str | bytes | bytearray):
        if isinstance(message, bytes | bytearray):
            return message.decode("utf-8")
        return message
    if is_compression_enabled():
        compressed = compress_json(message)
        return COMPRESSION_PREFIX + base64.b64encode(compressed).decode("ascii")
    return json.dumps(message, separators=(",", ":"))


def decode_payload(message: Any) -> Any:
    """Decode a transport payload back into a Python object.

    Detects the ``COMPRESSION_PREFIX`` and transparently decompresses.
    Falls back to plain JSON parsing for backward compatibility.
    """
    if isinstance(message, bytes | bytearray):
        message = message.decode("utf-8")
    if isinstance(message, str):
        if message.startswith(COMPRESSION_PREFIX):
            try:
                compressed = base64.b64decode(message[len(COMPRESSION_PREFIX) :])
                return decompress_json(compressed)
            except Exception:
                # Decompression failed — fall through to JSON parse as fallback
                pass
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return message
    return message
