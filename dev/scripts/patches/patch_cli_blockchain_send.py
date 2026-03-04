import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

new_commands = """
@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.option('--from', 'from_addr', required=True, help='Sender address')
@click.option('--to', required=True, help='Recipient address')
@click.option('--data', required=True, help='Transaction data payload')
@click.option('--nonce', type=int, default=0, help='Nonce')
@click.pass_context
def send(ctx, chain_id, from_addr, to, data, nonce):
    \"\"\"Send a transaction to a chain\"\"\"
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            tx_payload = {
                "type": "TRANSFER",
                "chain_id": chain_id,
                "from_address": from_addr,
                "to_address": to,
                "value": 0,
                "gas_limit": 100000,
                "gas_price": 1,
                "nonce": nonce,
                "data": data,
                "signature": "mock_signature"
            }
            
            response = client.post(
                f"http://127.0.0.1:8082/rpc/sendTx",
                json=tx_payload,
                timeout=5
            )
            if response.status_code in (200, 201):
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to send transaction: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")
"""

content = content + "\n" + new_commands

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
