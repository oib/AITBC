"""
Combined blockchain node and P2P service launcher
Runs both the main blockchain node, P2P placeholder service, and HTTP RPC server
"""

import asyncio
from typing import Any

import uvicorn

from aitbc.aitbc_logging import get_logger
from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.main import _run as run_node

logger = get_logger(__name__)


class CombinedService:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[Any]] = []
        self._http_server: Any = None

    async def start(self) -> None:
        """Start both blockchain node and HTTP RPC server"""
        logger.info("Starting combined blockchain service")
        node_task = asyncio.create_task(run_node())
        self._tasks.append(node_task)
        app = create_app()
        config = uvicorn.Config(app, host=settings.rpc_bind_host, port=settings.rpc_bind_port, log_level="info")
        self._http_server = uvicorn.Server(config)
        http_task = asyncio.create_task(self._http_server.serve())
        self._tasks.append(http_task)
        logger.info("Combined service started - Node on mainnet, RPC server on port %s", settings.rpc_bind_port)
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop all services"""
        logger.info("Stopping combined blockchain service")
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Combined service stopped")


async def main() -> None:
    """Main entry point"""
    service = CombinedService()
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
