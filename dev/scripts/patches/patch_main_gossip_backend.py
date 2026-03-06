import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "r") as f:
    content = f.read()

if "from .gossip import gossip_broker, create_backend" not in content:
    content = content.replace(
        "from .gossip import gossip_broker",
        "from .gossip import gossip_broker, create_backend"
    )

content = content.replace(
        """    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"supported_chains": getattr(settings, 'supported_chains', settings.chain_id)})
        init_db()
        init_mempool(
            backend=settings.mempool_backend,
            db_path=str(settings.db_path.parent / "mempool.db"),
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )""",
        """    async def start(self) -> None:
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
        )"""
)

content = content.replace(
    """    async def _shutdown(self) -> None:
        for chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()""",
    """    async def _shutdown(self) -> None:
        for chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()
        await gossip_broker.shutdown()"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "w") as f:
    f.write(content)
