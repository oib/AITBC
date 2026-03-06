import asyncio
from aitbc_cli.core.chain_manager import ChainManager
from aitbc_cli.core.config import load_multichain_config

async def test():
    config = load_multichain_config()
    manager = ChainManager(config)
    print("Nodes:", config.nodes)
    chains = await manager.list_chains()
    print("All chains:", [c.id for c in chains])
    
    chain = await manager._find_chain_on_nodes("ait-testnet")
    print("Found ait-testnet:", chain is not None)

if __name__ == "__main__":
    asyncio.run(test())
