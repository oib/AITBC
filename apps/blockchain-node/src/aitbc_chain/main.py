from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from .config import settings
from .consensus import PoAProposer, ProposerConfig, CircuitBreaker
from .database import init_db, session_scope
from .logger import get_logger
from .gossip import gossip_broker, create_backend
from .sync import ChainSync
from .mempool import init_mempool

logger = get_logger(__name__)


class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposers: dict[str, PoAProposer] = {}

    async def _setup_gossip_subscribers(self) -> None:
        # Transactions
        tx_sub = await gossip_broker.subscribe("transactions")
        
        async def process_txs():
            from .mempool import get_mempool
            mempool = get_mempool()
            while True:
                try:
                    tx_data = await tx_sub.queue.get()
                    if isinstance(tx_data, str):
                        import json
                        tx_data = json.loads(tx_data)
                    chain_id = tx_data.get("chain_id", "ait-devnet")
                    mempool.add(tx_data, chain_id=chain_id)
                except Exception as exc:
                    logger.error(f"Error processing transaction from gossip: {exc}")
                    
        asyncio.create_task(process_txs())

        # Blocks
        block_sub = await gossip_broker.subscribe("blocks")
        
        async def process_blocks():
            while True:
                try:
                    block_data = await block_sub.queue.get()
                    logger.info(f"Received block from gossip")
                    if isinstance(block_data, str):
                        import json
                        block_data = json.loads(block_data)
                    chain_id = block_data.get("chain_id", "ait-devnet")
                    logger.info(f"Importing block for chain {chain_id}: {block_data.get('height')}")
                    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)
                    res = sync.import_block(block_data)
                    logger.info(f"Import result: accepted={res.accepted}, reason={res.reason}")
                except Exception as exc:
                    logger.error(f"Error processing block from gossip: {exc}")
                    
        asyncio.create_task(process_blocks())

    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"supported_chains": getattr(settings, 'supported_chains', settings.chain_id)})
        
        # Initialize Gossip Backend
        backend = create_backend(
            settings.gossip_backend,
            broadcast_url=settings.gossip_broadcast_url,
        )
        await gossip_broker.set_backend(backend)
        
        init_db()
        init_mempool(
            backend=settings.mempool_backend,
            db_path=str(settings.db_path.parent / "mempool.db"),
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )
        self._start_proposers()
        await self._setup_gossip_subscribers()
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
        await gossip_broker.shutdown()


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
