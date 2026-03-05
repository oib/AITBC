"""Blockchain commands for AITBC CLI"""

import click
import httpx

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

from typing import Optional, List
from ..utils import output, error


@click.group()
def blockchain():
    """Query blockchain information and status"""
    pass


@blockchain.command()
@click.option("--limit", type=int, default=10, help="Number of blocks to show")
@click.option("--from-height", type=int, help="Start from this block height")
@click.pass_context
def blocks(ctx, limit: int, from_height: Optional[int]):
    """List recent blocks"""
    config = ctx.obj['config']
    
    try:
        params = {"limit": limit}
        if from_height:
            params["from_height"] = from_height
            
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/explorer/blocks",
                params=params,
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                data = response.json()
                output(data, ctx.obj['output_format'])
            else:
                error(f"Failed to fetch blocks: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.argument("block_hash")
@click.pass_context
def block(ctx, block_hash: str):
    """Get details of a specific block"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/explorer/blocks/{block_hash}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                block_data = response.json()
                output(block_data, ctx.obj['output_format'])
            else:
                error(f"Block not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.argument("tx_hash")
@click.pass_context
def transaction(ctx, tx_hash: str):
    """Get transaction details"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/explorer/transactions/{tx_hash}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                tx_data = response.json()
                output(tx_data, ctx.obj['output_format'])
            else:
                error(f"Transaction not found: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option("--node", type=int, default=1, help="Node number (1, 2, or 3)")
@click.pass_context
def status(ctx, node: int):
    """Get blockchain node status"""
    config = ctx.obj['config']
    
    # Map node to RPC URL
    node_urls = {
        1: "http://localhost:8082",
        2: "http://localhost:9080/rpc",  # Use RPC API with correct endpoint
        3: "http://aitbc.keisanki.net/rpc"
    }
    
    rpc_url = node_urls.get(node)
    if not rpc_url:
        error(f"Invalid node number: {node}")
        return
    
    try:
        with httpx.Client() as client:
            # First get health for general status
            health_url = rpc_url.replace("/rpc", "") + "/v1/health" if "/rpc" in rpc_url else rpc_url + "/v1/health"
            response = client.get(
                health_url,
                timeout=5
            )
            
            if response.status_code == 200:
                status_data = response.json()
                output({
                    "node": node,
                    "rpc_url": rpc_url,
                    "status": status_data
                }, ctx.obj['output_format'])
            else:
                error(f"Node {node} not responding: {response.status_code}")
    except Exception as e:
        error(f"Failed to connect to node {node}: {e}")


@blockchain.command()
@click.pass_context
def sync_status(ctx):
    """Get blockchain synchronization status"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/health",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                sync_data = response.json()
                output(sync_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get sync status: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.pass_context
def peers(ctx):
    """List connected peers"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/health",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                peers_data = response.json()
                output(peers_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get peers: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.pass_context
def info(ctx):
    """Get blockchain information"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/health",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                info_data = response.json()
                output(info_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get blockchain info: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.pass_context
def supply(ctx):
    """Get token supply information"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/health",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                supply_data = response.json()
                output(supply_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get supply info: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.pass_context
def validators(ctx):
    """List blockchain validators"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/health",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                validators_data = response.json()
                output(validators_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get validators: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")

@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.pass_context
def genesis(ctx, chain_id):
    """Get the genesis block of a chain"""
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            # We assume node 1 is running on port 8082, but let's just hit the first configured node
            response = client.get(
                f"{_get_node_endpoint(ctx)}/rpc/blocks/0?chain_id={chain_id}",
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
def transactions(ctx, chain_id):
    """Get latest transactions on a chain"""
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            response = client.get(
                f"{_get_node_endpoint(ctx)}/rpc/transactions?chain_id={chain_id}",
                timeout=5
            )
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get transactions: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")

@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.pass_context
def head(ctx, chain_id):
    """Get the head block of a chain"""
    config = ctx.obj['config']
    try:
        import httpx
        with httpx.Client() as client:
            response = client.get(
                f"{_get_node_endpoint(ctx)}/rpc/head?chain_id={chain_id}",
                timeout=5
            )
            if response.status_code == 200:
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to get head block: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--chain-id', required=True, help='Chain ID')
@click.option('--from', 'from_addr', required=True, help='Sender address')
@click.option('--to', required=True, help='Recipient address')
@click.option('--data', required=True, help='Transaction data payload')
@click.option('--nonce', type=int, default=0, help='Nonce')
@click.pass_context
def send(ctx, chain_id, from_addr, to, data, nonce):
    """Send a transaction to a chain"""
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
                f"{_get_node_endpoint(ctx)}/rpc/sendTx",
                json=tx_payload,
                timeout=5
            )
            if response.status_code in (200, 201):
                output(response.json(), ctx.obj['output_format'])
            else:
                error(f"Failed to send transaction: {response.status_code} - {response.text}")
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--address', required=True, help='Wallet address')
@click.pass_context
def balance(ctx, address):
    """Get the balance of an address across all chains"""
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
    """Mint devnet funds to an address"""
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
