from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from .config import settings
from .consensus import PoAProposer, ProposerConfig
from .database import init_db, session_scope
from .logging import get_logger

logger = get_logger(__name__)


class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposer: Optional[PoAProposer] = None

    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"chain_id": settings.chain_id})
        init_db()
        self._start_proposer()
        try:
            await self._stop_event.wait()
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        logger.info("Stopping blockchain node")
        self._stop_event.set()
        await self._shutdown()

    def _start_proposer(self) -> None:
        if self._proposer is not None:
            return

        proposer_config = ProposerConfig(
            chain_id=settings.chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
        )
        self._proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
        asyncio.create_task(self._proposer.start())

    async def _shutdown(self) -> None:
        if self._proposer is None:
            return
        await self._proposer.stop()
        self._proposer = None


@asynccontextmanager
async def node_app() -> asyncio.AbstractAsyncContextManager[BlockchainNode]:  # type: ignore[override]
    node = BlockchainNode()
    try:
        yield node
    finally:
        await node.stop()


def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    async with node_app() as node:
        await node.start()


if __name__ == "__main__":  # pragma: no cover
    run()
