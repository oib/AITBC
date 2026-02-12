"""Blockchain commands for AITBC CLI"""

import click
import httpx
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
                f"{config.coordinator_url}/v1/explorer/blocks",
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
                f"{config.coordinator_url}/v1/explorer/blocks/{block_hash}",
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
                f"{config.coordinator_url}/v1/explorer/transactions/{tx_hash}",
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
        2: "http://localhost:8081", 
        3: "http://aitbc.keisanki.net/rpc"
    }
    
    rpc_url = node_urls.get(node)
    if not rpc_url:
        error(f"Invalid node number: {node}")
        return
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{rpc_url}/status",
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
                f"{config.coordinator_url}/v1/blockchain/sync",
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
                f"{config.coordinator_url}/v1/blockchain/peers",
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
                f"{config.coordinator_url}/v1/blockchain/info",
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
                f"{config.coordinator_url}/v1/blockchain/supply",
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
                f"{config.coordinator_url}/v1/blockchain/validators",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                validators_data = response.json()
                output(validators_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get validators: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
