"""
Module-level singleton for the in-process block header cache.

Imported by ``rpc/blocks.py`` (hot-path reads) and ``consensus/poa.py``
(invalidation on new block import).  Using a shared singleton ensures all
components see the same cache state without passing an instance around.
"""

from aitbc.caching import BlockHeaderCache

# Singleton instance shared across the node process.
block_header_cache = BlockHeaderCache(max_size=1000)


def get_block_header_cache() -> BlockHeaderCache:
    """Return the process-wide :class:`BlockHeaderCache` singleton."""
    return block_header_cache
