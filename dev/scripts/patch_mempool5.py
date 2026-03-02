with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Fix DatabaseMempool.add() call in router.py - the problem was `mempool.add(tx_dict, chain_id)` which is 3 positional arguments (self, tx, chain_id).
# Wait, `def add(self, tx: Dict[str, Any], chain_id: str = "ait-devnet") -> str:`
# `mempool.add(tx_dict, chain_id)` shouldn't raise "takes 2 positional arguments but 3 were given" unless `get_mempool()` is returning `InMemoryMempool` instead of `DatabaseMempool`.

# Let's check init_mempool in main.py, it uses MEMPOOL_BACKEND from config.
# If MEMPOOL_BACKEND="database" then it should be DatabaseMempool.

content = content.replace(
    "tx_hash = mempool.add(tx_dict, chain_id)",
    "tx_hash = mempool.add(tx_dict, chain_id=chain_id)" # try keyword
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
