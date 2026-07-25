"""Redis edge cache for wallet-bound theme preferences (v0.17.0 §B3).

ponytail: This cache is intended to keep preference hydration under 100ms at
edge nodes. It falls back to an in-memory dict when Redis is not available.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def _make_key(wallet_address: str) -> str:
    """Return a Redis key for a wallet preference."""
    return f"aitbc:theme:{wallet_address.lower()}"


class ThemePreferenceCache:
    """Edge cache for agent wallet theme preferences."""

    def __init__(self, redis_url: str | None = None, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._fallback: dict[str, Any] = {}
        self._client: Any | None = None
        redis_url = redis_url or os.getenv("REDIS_URL", "")

        if redis_url:
            try:
                import redis

                self._client = redis.from_url(redis_url, decode_responses=True)
                self._client.ping()
                logger.info("ThemePreferenceCache connected to Redis")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis unavailable, using in-memory fallback: %s", exc)
                self._client = None

    def get(self, wallet_address: str) -> dict[str, Any] | None:
        """Return cached preference or None."""
        key = _make_key(wallet_address)
        if self._client is not None:
            try:
                raw = self._client.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis read failed for %s: %s", wallet_address, exc)
        return self._fallback.get(key)

    def set(self, wallet_address: str, preference: dict[str, Any]) -> None:
        """Cache a theme preference."""
        key = _make_key(wallet_address)
        payload = json.dumps(preference)
        if self._client is not None:
            try:
                self._client.set(key, payload, ex=self._ttl)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis write failed for %s: %s", wallet_address, exc)
        self._fallback[key] = preference

    def delete(self, wallet_address: str) -> None:
        """Remove a cached preference."""
        key = _make_key(wallet_address)
        if self._client is not None:
            try:
                self._client.delete(key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis delete failed for %s: %s", wallet_address, exc)
        self._fallback.pop(key, None)
