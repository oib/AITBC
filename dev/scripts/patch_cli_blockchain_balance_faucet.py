import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

new_commands = """
@blockchain.command()
@click.option('--address', required=True, help='Wallet address')
@click.pass_context
def balance(ctx, address):
    \"\"\"Get the balance of an address across all chains\"\"\"
    config = ctx.obj['config']
    try:
        import httpx
        # Balance is typically served by the coordinator API or blockchain node directly
        # The node has /rpc/getBalance/{address} but it expects chain_id param. Let's just query devnet for now.
        with httpx.Client() as client:
            response = client.get(
                f"{_get_node_endpoint(ctx)}/rpc/getBalance/{address}?chain_id=ait-devnet",
                timeout=5
            )
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get balance: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")

@blockchain.command()
@click.option('--address', required=True, help='Wallet address')
@click.option('--amount', type=int, default=1000, help='Amount to mint')
@click.pass_context
def faucet(ctx, address, amount):
    \"\"\"Mint devnet funds to an address\"\"\"
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            response = client.post(
                f"{_get_node_endpoint(ctx)}/rpc/admin/mintFaucet",
                json={"address": address, "amount": amount, "chain_id": "ait-devnet"},
                timeout=5
            )
            if response.status_code in (200, 201):
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to use faucet: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")
"""

content = content + "\n" + new_commands

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
