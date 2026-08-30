"""Optional in-process HTTP status endpoint for SyncManager.

This runs inside the aitbc-blockchain-node process so operators and
monitoring can inspect the per-chain sync state without importing
SyncManager directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from uvicorn import Config, Server

from .sync_manager import SyncManager


class SyncManagerStatusServer:
    """Small HTTP server exposing /sync/status and /health."""

    def __init__(self, sync_manager: SyncManager, host: str = "0.0.0.0", port: int = 8204) -> None:
        self._sync_manager = sync_manager
        self._host = host
        self._port = port
        self._server: Server | None = None

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="AITBC SyncManager Status", version="v0.1.0")

        @app.get("/sync/status")
        async def sync_status() -> dict[str, Any]:
            chains = {cid: self._sync_manager.get_sync_status(cid) for cid in self._sync_manager._chains}
            return {"chains": chains}

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        return app

    async def start(self) -> None:
        app = self._create_app()
        config = Config(app, host=self._host, port=self._port, log_level="critical")
        self._server = Server(config)
        await self._server.serve()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
