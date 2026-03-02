import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Instead of blindly hardcoding 10.1.223.93, we can actually fetch the first node from multichain config or use an option --node.
# Let's add a helper inside the file.
helper_code = """
def _get_node_endpoint(ctx):
    try:
        from ..core.config import load_multichain_config
        config = load_multichain_config()
        if not config.nodes:
            return "http://127.0.0.1:8082"
        # Return the first node's endpoint
        return list(config.nodes.values())[0].endpoint
    except:
        return "http://127.0.0.1:8082"
"""

# Replace the hardcoded urls with _get_node_endpoint(ctx)
content = content.replace('f"http://10.1.223.93:8082/rpc/blocks/0?chain_id={chain_id}"', 'f"{_get_node_endpoint(ctx)}/rpc/blocks/0?chain_id={chain_id}"')
content = content.replace('f"http://10.1.223.93:8082/rpc/mempool?chain_id={chain_id}"', 'f"{_get_node_endpoint(ctx)}/rpc/mempool?chain_id={chain_id}"')
content = content.replace('f"http://10.1.223.93:8082/rpc/head?chain_id={chain_id}"', 'f"{_get_node_endpoint(ctx)}/rpc/head?chain_id={chain_id}"')
content = content.replace('f"http://10.1.223.93:8082/rpc/sendTx"', 'f"{_get_node_endpoint(ctx)}/rpc/sendTx"')

# Prepend the helper
content = content.replace('import httpx', 'import httpx\n' + helper_code, 1)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
