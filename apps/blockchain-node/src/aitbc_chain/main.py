from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from .config import settings
from .consensus import PoAProposer, ProposerConfig, CircuitBreaker
from .database import init_db, session_scope
from .logger import get_logger
from .mempool import init_mempool

logger = get_logger(__name__)


class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposers: dict[str, PoAProposer] = {}

    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"supported_chains": getattr(settings, 'supported_chains', settings.chain_id)})
        init_db()
        init_mempool(
            backend=settings.mempool_backend,
            db_path=str(settings.db_path.parent / "mempool.db"),
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )
        self._start_proposers()
        try:
            await self._stop_event.wait()
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        logger.info("Stopping blockchain node")
        self._stop_event.set()
        await self._shutdown()

    def _start_proposers(self) -> None:
        chains_str = getattr(settings, 'supported_chains', settings.chain_id)
        chains = [c.strip() for c in chains_str.split(",") if c.strip()]
        for chain_id in chains:
            if chain_id in self._proposers:
                continue

            proposer_config = ProposerConfig(
                chain_id=chain_id,
                proposer_id=settings.proposer_id,
                interval_seconds=settings.block_time_seconds,
                max_block_size_bytes=settings.max_block_size_bytes,
                max_txs_per_block=settings.max_txs_per_block,
            )
            
            proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
            self._proposers[chain_id] = proposer
            asyncio.create_task(proposer.start())

    async def _shutdown(self) -> None:
        for chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()


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
