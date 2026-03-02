import asyncio
from aitbc_cli.core.config import NodeConfig
from aitbc_cli.core.node_client import NodeClient

async def test():
    config = NodeConfig(id="aitbc-primary", endpoint="http://10.1.223.93:8082")
    async with NodeClient(config) as client:
        print("Connected.")
        chains = await client.get_hosted_chains()
        print("Chains:", chains)

asyncio.run(test())
