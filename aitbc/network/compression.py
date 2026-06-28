"""
Compression utilities for network payloads.

Provides gzip and zstd compression/decompression helpers for block and
transaction data sent over the network (gossip, P2P TCP, Redis pub/sub).

Usage::

    from aitbc.network import compress_json, decompress_json

    payload = compress_json(block_data)       # bytes
    block = decompress_json(payload)          # dict
"""

import gzip
import json
import zlib
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Check if zstandard is available (optional, preferred for better ratio)
try:
    import zstandard as zstd  # type: ignore[import-not-found]

    _ZSTD_AVAILABLE = True
except ImportError:
    _ZSTD_AVAILABLE = False


def compress(data: bytes | str, algorithm: str = "gzip") -> bytes:
    """Compress raw bytes or a string.

    Args:
        data: Bytes or string to compress.
        algorithm: ``"gzip"`` (default, stdlib), ``"zstd"`` (if zstandard installed),
                   or ``"zlib"`` (stdlib, fastest).

    Returns:
        Compressed bytes.

    Raises:
        ValueError: If algorithm is unknown or zstd requested but not installed.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    if algorithm == "gzip":
        return gzip.compress(data)
    elif algorithm == "zlib":
        return zlib.compress(data)
    elif algorithm == "zstd":
        if not _ZSTD_AVAILABLE:
            raise ValueError("zstd requested but 'zstandard' package is not installed")
        return zstd.compress(data)  # type: ignore[no-any-return]
    else:
        raise ValueError(f"Unknown compression algorithm: {algorithm}")


def decompress(data: bytes, algorithm: str = "gzip") -> bytes:
    """Decompress bytes.

    Args:
        data: Compressed bytes.
        algorithm: Must match the algorithm used to compress.

    Returns:
        Decompressed bytes.

    Raises:
        ValueError: If algorithm is unknown or zstd requested but not installed.
    """
    if algorithm == "gzip":
        return gzip.decompress(data)
    elif algorithm == "zlib":
        return zlib.decompress(data)
    elif algorithm == "zstd":
        if not _ZSTD_AVAILABLE:
            raise ValueError("zstd requested but 'zstandard' package is not installed")
        return zstd.decompress(data)  # type: ignore[no-any-return]
    else:
        raise ValueError(f"Unknown compression algorithm: {algorithm}")


def compress_json(obj: Any, algorithm: str = "gzip") -> bytes:
    """Serialize an object to compact JSON and compress it.

    Args:
        obj: Any JSON-serializable object.
        algorithm: Compression algorithm (default ``"gzip"``).

    Returns:
        Compressed bytes.
    """
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return compress(raw, algorithm=algorithm)


def decompress_json(data: bytes, algorithm: str = "gzip") -> Any:
    """Decompress bytes and parse as JSON.

    Args:
        data: Compressed JSON bytes.
        algorithm: Must match the algorithm used to compress.

    Returns:
        The deserialized Python object.
    """
    raw = decompress(data, algorithm=algorithm)
    return json.loads(raw.decode("utf-8"))


def compression_ratio(original: bytes, compressed: bytes) -> float:
    """Calculate compression ratio as a percentage (0-100).

    A ratio of 60% means the compressed data is 60% smaller than the original.
    """
    if not original:
        return 0.0
    return (1.0 - len(compressed) / len(original)) * 100.0
