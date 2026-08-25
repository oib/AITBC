"""Long-running sync service entry point."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

from aitbc.aitbc_logging import configure_logging, get_logger

from .config import settings
from .sync_manager import SyncManager

configure_logging(
    level=os.getenv("AITBC_LOG_LEVEL", getattr(settings, "log_level", "INFO")),
    service_name="blockchain-sync",
    to_file=True,
)
logger = get_logger(__name__)


async def main() -> None:
    manager = SyncManager()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop(*_: Any) -> None:
        logger.info("Received stop signal")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop)

    try:
        await manager.start()
        await stop_event.wait()
    finally:
        await manager.stop()

    logger.info("Sync service stopped")


if __name__ == "__main__":
    asyncio.run(main())
