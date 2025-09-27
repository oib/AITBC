from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from .config import MinerSettings, settings
from .logging import get_logger

logger = get_logger(__name__)


class CoordinatorClient:
    """Async HTTP client for interacting with the coordinator API."""

    def __init__(self, cfg: MinerSettings | None = None) -> None:
        self.cfg = cfg or settings
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Authorization": f"Bearer {self.cfg.auth_token}",
                "User-Agent": f"aitbc-miner/{self.cfg.node_id}",
            }
            timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=None)
            self._client = httpx.AsyncClient(base_url=self.cfg.coordinator_base_url.rstrip("/"), headers=headers, timeout=timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.debug("registering miner", extra={"payload": payload})
        resp = await self.client.post("/miners/register", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def heartbeat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = await self.client.post("/miners/heartbeat", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def poll(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        resp = await self.client.post("/miners/poll", json=payload)
        if resp.status_code == 204:
            logger.debug("no job available")
            return None
        resp.raise_for_status()
        return resp.json()

    async def submit_result(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = await self.client.post(f"/miners/{job_id}/result", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def submit_failure(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = await self.client.post(f"/miners/{job_id}/fail", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def __aenter__(self) -> "CoordinatorClient":
        _ = self.client
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()


async def backoff(base: float, max_seconds: float) -> float:
    await asyncio.sleep(base)
    return min(base * 2, max_seconds)
