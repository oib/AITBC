import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Since /rpc/mempool doesn't exist on the node, let's remove it and use an endpoint that exists like /rpc/transactions
# Wait, /rpc/transactions exists! Let's rename the mempool command to transactions
content = content.replace('f"{_get_node_endpoint(ctx)}/rpc/mempool?chain_id={chain_id}"', 'f"{_get_node_endpoint(ctx)}/rpc/transactions?chain_id={chain_id}"')
content = content.replace('def mempool(ctx, chain_id):', 'def transactions(ctx, chain_id):')
content = content.replace('Get the mempool status of a chain', 'Get latest transactions on a chain')
content = content.replace('Failed to get mempool', 'Failed to get transactions')

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
