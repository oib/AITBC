"""
In-process LRU cache for block headers.

Provides fast access to recently-seen block headers without a Redis round-trip.
Designed for the block import / RPC hot path where the same headers are accessed
repeatedly within a short window.
"""

from collections import OrderedDict
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class BlockHeaderCache:
    """In-process LRU cache for block headers, keyed by chain_id + height/hash.

    Thread-safety: blockchain-node processes blocks sequentially in a single
    asyncio task, so a plain dict is sufficient. If concurrent access is later
    needed, wrap with an asyncio.Lock.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        # Keyed by (chain_id, height) and (chain_id, hash_lower)
        self._by_height: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()
        self._by_hash: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()

    def get(self, height: int, chain_id: str) -> dict[str, Any] | None:
        """Get a block header by (chain_id, height). Returns None on miss."""
        key = (chain_id, height)
        if key in self._by_height:
            self._by_height.move_to_end(key)
            return self._by_height[key]
        return None

    def get_by_hash(self, hash: str, chain_id: str) -> dict[str, Any] | None:
        """Get a block header by (chain_id, hash). Returns None on miss."""
        key = (chain_id, hash.lower())
        if key in self._by_hash:
            self._by_hash.move_to_end(key)
            return self._by_hash[key]
        return None

    def set(self, header: dict[str, Any], chain_id: str) -> None:
        """Insert/update a block header in the cache.

        The header dict must contain ``height`` and ``hash`` keys.
        """
        height = header.get("height")
        block_hash = header.get("hash")
        if height is None or block_hash is None:
            logger.warning("BlockHeaderCache.set: header missing 'height' or 'hash' — skipping")
            return

        h_key = (chain_id, int(height))
        hash_key = (chain_id, str(block_hash).lower())

        # Evict old entries if they exist (so move_to_end is correct).
        # If the height is being updated with a new hash, also clean up the
        # old hash entry — otherwise it becomes a stale orphan.
        old_by_height = self._by_height.pop(h_key, None)
        if old_by_height and old_by_height.get("hash"):
            self._by_hash.pop((chain_id, str(old_by_height["hash"]).lower()), None)
        old_by_hash = self._by_hash.pop(hash_key, None)
        if old_by_hash and old_by_hash.get("height") is not None:
            self._by_height.pop((chain_id, int(old_by_hash["height"])), None)

        self._by_height[h_key] = header
        self._by_hash[hash_key] = header

        self._evict()

    def invalidate(self, chain_id: str, height: int | None = None, hash: str | None = None) -> None:
        """Remove a block header from the cache by height and/or hash."""
        if height is not None:
            h_key = (chain_id, height)
            header = self._by_height.pop(h_key, None)
            if header and header.get("hash"):
                self._by_hash.pop((chain_id, str(header["hash"]).lower()), None)
        if hash is not None:
            hash_key = (chain_id, hash.lower())
            header = self._by_hash.pop(hash_key, None)
            if header and header.get("height") is not None:
                self._by_height.pop((chain_id, int(header["height"])), None)

    def clear(self) -> None:
        """Remove all entries."""
        self._by_height.clear()
        self._by_hash.clear()

    def __len__(self) -> int:
        return len(self._by_height)

    @property
    def size(self) -> int:
        """Number of cached headers."""
        return len(self._by_height)

    def _evict(self) -> None:
        """Evict least-recently-used entries when over capacity."""
        while len(self._by_height) > self.max_size:
            h_key, header = self._by_height.popitem(last=False)
            if header and header.get("hash"):
                self._by_hash.pop((h_key[0], str(header["hash"]).lower()), None)
