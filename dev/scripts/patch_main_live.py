with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "r") as f:
    content = f.read()

content = content.replace(
    """    def _start_proposer(self) -> None:
        if self._proposer is not None:
            return

        proposer_config = ProposerConfig(
            chain_id=settings.chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
            max_block_size_bytes=settings.max_block_size_bytes,
            max_txs_per_block=settings.max_txs_per_block,
        )
        cb = CircuitBreaker(
            threshold=settings.circuit_breaker_threshold,
            timeout=settings.circuit_breaker_timeout,
        )
        self._proposer = PoAProposer(config=proposer_config, session_factory=session_scope, circuit_breaker=cb)
        asyncio.create_task(self._proposer.start())""",
    """    def _start_proposer(self) -> None:
        if self._proposer is not None:
            return

        proposer_config = ProposerConfig(
            chain_id=settings.chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
            max_block_size_bytes=settings.max_block_size_bytes,
            max_txs_per_block=settings.max_txs_per_block,
        )
        self._proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
        asyncio.create_task(self._proposer.start())"""
)

# And actually we want the multi-chain one
content = content.replace(
    """class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposer: Optional[PoAProposer] = None""",
    """class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposers: dict[str, PoAProposer] = {}"""
)

content = content.replace(
    """    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"chain_id": settings.chain_id})
        init_db()
        init_mempool(
            backend=settings.mempool_backend,
            db_path=str(settings.db_path.parent / "mempool.db"),
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )
        self._start_proposer()
        try:
            await self._stop_event.wait()
        finally:
            await self._shutdown()""",
    """    async def start(self) -> None:
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
            await self._shutdown()"""
)

content = content.replace(
    """    def _start_proposer(self) -> None:
        if self._proposer is not None:
            return

        proposer_config = ProposerConfig(
            chain_id=settings.chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
            max_block_size_bytes=settings.max_block_size_bytes,
            max_txs_per_block=settings.max_txs_per_block,
        )
        self._proposer = PoAProposer(config=proposer_config, session_factory=session_scope)
        asyncio.create_task(self._proposer.start())""",
    """    def _start_proposers(self) -> None:
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
            asyncio.create_task(proposer.start())"""
)

content = content.replace(
    """    async def _shutdown(self) -> None:
        if self._proposer is None:
            return
        await self._proposer.stop()
        self._proposer = None""",
    """    async def _shutdown(self) -> None:
        for chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "w") as f:
    f.write(content)
