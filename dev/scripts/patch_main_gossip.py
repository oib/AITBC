import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "r") as f:
    content = f.read()

if "from .gossip import gossip_broker" not in content:
    content = content.replace(
        "from .logger import get_logger",
        "from .logger import get_logger\nfrom .gossip import gossip_broker\nfrom .sync import ChainSync"
    )

if "_setup_gossip_subscribers" not in content:
    content = content.replace(
        """    async def start(self) -> None:""",
        """    async def _setup_gossip_subscribers(self) -> None:
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
                    if isinstance(block_data, str):
                        import json
                        block_data = json.loads(block_data)
                    chain_id = block_data.get("chain_id", "ait-devnet")
                    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)
                    sync.import_block(block_data)
                except Exception as exc:
                    logger.error(f"Error processing block from gossip: {exc}")
                    
        asyncio.create_task(process_blocks())

    async def start(self) -> None:"""
    )
    
    content = content.replace(
        """        self._start_proposers()
        try:""",
        """        self._start_proposers()
        await self._setup_gossip_subscribers()
        try:"""
    )

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "w") as f:
    f.write(content)
