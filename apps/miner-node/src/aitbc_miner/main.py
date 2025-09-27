from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)


class MinerApplication:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        logger.info("Miner node starting", extra={"node_id": settings.node_id})
        # TODO: initialize capability probe, register with coordinator, start heartbeat and poll loops
        await self._stop_event.wait()

    async def stop(self) -> None:
        logger.info("Miner node shutting down")
        self._stop_event.set()


@asynccontextmanager
async def miner_app() -> AsyncIterator[MinerApplication]:
    app = MinerApplication()
    try:
        yield app
    finally:
        await app.stop()


def run() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run() -> None:
        async with miner_app() as app:
            loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(app.stop()))
            loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(app.stop()))
            await app.start()

    loop.run_until_complete(_run())


if __name__ == "__main__":  # pragma: no cover
    run()
