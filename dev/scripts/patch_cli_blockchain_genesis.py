import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Add blockchain genesis and blockchain mempool and blockchain head
new_commands = """@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.pass_context
def genesis(ctx, chain_id):
    \"\"\"Get the genesis block of a chain\"\"\"
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            # We assume node 1 is running on port 8082, but let's just hit the first configured node
            response = client.get(
                f"http://127.0.0.1:8082/rpc/blocks/0?chain_id={chain_id}",
                timeout=5
            )
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get genesis block: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")

@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.pass_context
def mempool(ctx, chain_id):
    \"\"\"Get the mempool status of a chain\"\"\"
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            response = client.get(
                f"http://127.0.0.1:8082/rpc/mempool?chain_id={chain_id}",
                timeout=5
            )
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get mempool: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")

@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.pass_context
def head(ctx, chain_id):
    \"\"\"Get the head block of a chain\"\"\"
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            response = client.get(
                f"http://127.0.0.1:8082/rpc/head?chain_id={chain_id}",
                timeout=5
            )
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get head block: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")
"""

content = content + "\n" + new_commands

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
