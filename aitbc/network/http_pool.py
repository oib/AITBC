"""
Shared async HTTP client with connection pooling.

Provides a singleton ``httpx.AsyncClient`` so that callers across the
blockchain-node reuse TCP connections instead of creating a new client
(and new connection pool) per request.
"""

from typing import Any

import httpx

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class SharedHttpClient:
    """Singleton async HTTP client with configurable connection pool limits.

    Usage::

        from aitbc.network import SharedHttpClient

        client = SharedHttpClient()
        resp = await client.get("http://localhost:8202/rpc/block/1")
        # ... later, in another module ...
        client2 = SharedHttpClient()  # same underlying client
        resp2 = await client2.post("http://localhost:8202/rpc/transaction", json=tx)
        # Clean up at shutdown:
        await SharedHttpClient.close_instance()
    """

    _instance: "SharedHttpClient | None" = None
    _client: httpx.AsyncClient | None = None

    def __new__(
        cls,
        max_connections: int = 100,
        max_keepalive: int = 20,
        timeout: float = 30.0,
    ) -> "SharedHttpClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        max_connections: int = 100,
        max_keepalive: int = 20,
        timeout: float = 30.0,
    ) -> None:
        # __new__ already set the attrs; __init__ is called every time,
        # so only set on first init (when _client is None).
        if not hasattr(self, "_initialized"):
            self._max_connections = max_connections
            self._max_keepalive = max_keepalive
            self._timeout = timeout
            self._initialized = True

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init the underlying httpx.AsyncClient."""
        if SharedHttpClient._client is None:
            limits = httpx.Limits(
                max_connections=self._max_connections,
                max_keepalive_connections=self._max_keepalive,
            )
            SharedHttpClient._client = httpx.AsyncClient(timeout=self._timeout, limits=limits)
            logger.info(
                "SharedHttpClient initialized (max_connections=%d, max_keepalive=%d, timeout=%.1fs)",
                self._max_connections,
                self._max_keepalive,
                self._timeout,
            )
        return SharedHttpClient._client

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform an async GET request using the shared client."""
        return await self._get_client().get(url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform an async POST request using the shared client."""
        return await self._get_client().post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform an async PUT request using the shared client."""
        return await self._get_client().put(url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform an async DELETE request using the shared client."""
        return await self._get_client().delete(url, **kwargs)

    @classmethod
    async def close_instance(cls) -> None:
        """Close the singleton client. Call at application shutdown."""
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
            logger.info("SharedHttpClient closed")
        cls._instance = None

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing). Does NOT close the client —
        use ``close_instance`` first if the client was initialized."""
        cls._instance = None
        cls._client = None
