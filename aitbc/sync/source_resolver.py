"""Sync source resolution for multi-island node support.

Provides per-chain hub URL resolution from the CHAIN_SYNC_SOURCES config string,
with fallback to a default URL for chains not explicitly mapped.
"""

from __future__ import annotations


class SyncSourceResolver:
    """Resolves sync source URLs per chain_id.

    Parses the CHAIN_SYNC_SOURCES config string (format:
    "chain_id:url,chain_id:url,...") and provides per-chain hub URL
    resolution with fallback to a default URL.
    """

    def __init__(self, sync_sources: str = "", default_url: str | None = None) -> None:
        """Initialize with config string and default fallback URL.

        Args:
            sync_sources: Comma-separated "chain_id:url" pairs.
            default_url: Fallback URL for chains not in the mapping.
        """
        self._sources: dict[str, str] = self._parse_sync_sources(sync_sources)
        self._default_url = self._normalize_url(default_url) if default_url else default_url

    @staticmethod
    def _parse_sync_sources(sync_sources: str) -> dict[str, str]:
        """Parse the sync sources config string.

        Format: "chain_id:url,chain_id:url,..."
        Returns dict mapping chain_id → url.
        Raises ValueError for malformed entries.
        """
        if not sync_sources or not sync_sources.strip():
            return {}
        result: dict[str, str] = {}
        for entry in sync_sources.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                raise ValueError(f"Invalid sync source entry (expected 'chain_id:url'): {entry}")
            # Split on first colon only (URL may contain colons)
            chain_id, url = entry.split(":", 1)
            chain_id = chain_id.strip()
            url = url.strip()
            if not chain_id or not url:
                raise ValueError(f"Invalid sync source entry (empty chain_id or url): {entry}")
            url = SyncSourceResolver._normalize_url(url)
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"http://{url}"
            result[chain_id] = url
        return result

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip trailing junk that breaks httpx port parsing.

        A trailing ``:`` or ``/`` in an env-provided URL (e.g.
        ``http://127.0.0.1:8302:``) makes every poll raise
        ``InvalidURL``/``ValueError`` inside the sync loop instead of
        failing fast (#1663). Normalizing here covers both the per-chain
        map and the default fallback, which bypasses _parse_sync_sources.
        """
        return url.strip().rstrip("/").rstrip(":") if url else url

    def get_sync_source(self, chain_id: str) -> str | None:
        """Resolve sync source URL for a given chain_id.

        1. Check the per-chain mapping
        2. Fall back to default_url
        """
        if chain_id in self._sources:
            return self._sources[chain_id]
        return self._default_url

    def get_all_sources(self) -> dict[str, str]:
        """Return all configured sync sources (chain_id → url)."""
        return dict(self._sources)

    def has_per_chain_sources(self) -> bool:
        """Return True if per-chain sources are configured (non-empty mapping)."""
        return bool(self._sources)

    def is_fallback_source(self, chain_id: str) -> bool:
        """Return True if the resolved source for this chain is the default fallback.

        A chain that falls back to the default peer is typically one the node does
        not explicitly map.  Followers should not try to pull such a chain from the
        default hub unless they do not produce it locally.
        """
        return chain_id not in self._sources
