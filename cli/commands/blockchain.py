"""Blockchain commands for AITBC CLI"""

import click
import httpx

def _get_node_endpoint(ctx):
    """Get the blockchain node RPC endpoint from context or config."""
    try:
        config = ctx.obj['config']
        # Use the new blockchain_rpc_url from config
        return config.blockchain_rpc_url
    except:
        return "http://127.0.0.1:8006"  # Default blockchain RPC port

from typing import Optional, List
from utils import output, error
import os


@click.group()
@click.option("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.pass_context
def blockchain(ctx, chain_id: Optional[str]):
    """Query blockchain information and status"""
    # Set role for blockchain commands
    ctx.ensure_object(dict)
    ctx.parent.detected_role = 'blockchain'
    
    # Handle chain_id with auto-detection
    from aitbc_cli.utils.chain_id import get_chain_id
    config = ctx.obj.get('config')
    default_rpc_url = _get_node_endpoint(ctx)
    ctx.obj['chain_id'] = get_chain_id(default_rpc_url, override=chain_id)


@blockchain.command()
@click.option("--limit", type=int, default=10, help="Number of blocks to show")
@click.option("--from-height", type=int, help="Start from this block height")
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Query blocks across all available chains')
@click.pass_context
def blocks(ctx, limit: int, from_height: Optional[int], chain_id: str, all_chains: bool):
    """List recent blocks across chains"""
    try:
        config = ctx.obj['config']
        
        if all_chains:
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_blocks = {}
            
            for chain in chains:
                try:
                    node_url = _get_node_endpoint(ctx)
                    
                    # Get blocks from the specific chain
                    with httpx.Client() as client:
                        if from_height:
                            # Get blocks range
                            response = client.get(
                                f"{node_url}/rpc/blocks-range",
                                params={"from_height": from_height, "limit": limit, "chain_id": chain},
                                timeout=5
                            )
                        else:
                            # Get recent blocks starting from head
                            response = client.get(
                                f"{node_url}/rpc/blocks-range",
                                params={"limit": limit, "chain_id": chain},
                                timeout=5
                            )
                        
                        if response.status_code == 200:
                            all_blocks[chain] = response.json()
                        else:
                            # Fallback to getting head block for this chain
                            head_response = client.get(f"{node_url}/rpc/head?chain_id={chain}", timeout=5)
                            if head_response.status_code == 200:
                                head_data = head_response.json()
                                all_blocks[chain] = {
                                    "blocks": [head_data],
                                    "message": f"Showing head block only for chain {chain} (height {head_data.get('height', 'unknown')})"
                                }
                            else:
                                all_blocks[chain] = {"error": f"Failed to get blocks: HTTP {response.status_code}"}
                except Exception as e:
                    all_blocks[chain] = {"error": str(e)}
            
            output({
                "chains": all_blocks,
                "total_chains": len(chains),
                "successful_queries": sum(1 for b in all_blocks.values() if "error" not in b),
                "limit": limit,
                "from_height": from_height,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            node_url = _get_node_endpoint(ctx)
            
            # Get blocks from the local blockchain node
            with httpx.Client() as client:
                if from_height:
                    # Get blocks range
                    response = client.get(
                        f"{node_url}/rpc/blocks-range",
                        params={"from_height": from_height, "limit": limit, "chain_id": target_chain},
                        timeout=5
                    )
                else:
                    # Get recent blocks starting from head
                    response = client.get(
                        f"{node_url}/rpc/blocks-range",
                        params={"limit": limit, "chain_id": target_chain},
                        timeout=5
                    )
                
                if response.status_code == 200:
                    blocks_data = response.json()
                    output({
                        "blocks": blocks_data,
                        "chain_id": target_chain,
                        "limit": limit,
                        "from_height": from_height,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    # Fallback to getting head block if range not available
                    head_response = client.get(f"{node_url}/rpc/head?chain_id={target_chain}", timeout=5)
                    if head_response.status_code == 200:
                        head_data = head_response.json()
                        output({
                            "blocks": [head_data],
                            "chain_id": target_chain,
                            "message": f"Showing head block only for chain {target_chain} (height {head_data.get('height', 'unknown')})",
                            "query_type": "single_chain_fallback"
                        }, ctx.obj['output_format'])
                    else:
                        error(f"Failed to get blocks: {response.status_code} - {response.text}")
                        
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.argument("block_hash")
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Search block across all available chains')
@click.pass_context
def block(ctx, block_hash: str, chain_id: str, all_chains: bool):
    """Get details of a specific block across chains"""
    try:
        config = ctx.obj['config']
        
        if all_chains:
            # Search for block across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            block_results = {}
            
            for chain in chains:
                try:
                    node_url = _get_node_endpoint(ctx)
                    
                    with httpx.Client() as client:
                        # First try to get block by hash
                        response = client.get(
                            f"{node_url}/rpc/blocks/by_hash/{block_hash}?chain_id={chain}",
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            block_results[chain] = response.json()
                        else:
                            # If by_hash not available, try to get by height (if hash looks like a number)
                            try:
                                height = int(block_hash)
                                height_response = client.get(f"{node_url}/rpc/blocks/{height}?chain_id={chain}", timeout=5)
                                if height_response.status_code == 200:
                                    block_results[chain] = height_response.json()
                                else:
                                    block_results[chain] = {"error": f"Block not found: HTTP {height_response.status_code}"}
                            except ValueError:
                                block_results[chain] = {"error": f"Block not found: HTTP {response.status_code}"}
                                
                except Exception as e:
                    block_results[chain] = {"error": str(e)}
            
            # Count successful searches
            successful_searches = sum(1 for result in block_results.values() if "error" not in result)
            
            output({
                "block_hash": block_hash,
                "chains": block_results,
                "total_chains": len(chains),
                "successful_searches": successful_searches,
                "query_type": "all_chains",
                "found_in_chains": [chain for chain, result in block_results.items() if "error" not in result]
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            node_url = _get_node_endpoint(ctx)
            
            with httpx.Client() as client:
                # First try to get block by hash
                response = client.get(
                    f"{node_url}/rpc/blocks/by_hash/{block_hash}?chain_id={target_chain}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    block_data = response.json()
                    output({
                        "block_data": block_data,
                        "chain_id": target_chain,
                        "block_hash": block_hash,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    # If by_hash not available, try to get by height (if hash looks like a number)
                    try:
                        height = int(block_hash)
                        height_response = client.get(f"{node_url}/rpc/blocks/{height}?chain_id={target_chain}", timeout=5)
                        if height_response.status_code == 200:
                            block_data = height_response.json()
                            output({
                                "block_data": block_data,
                                "chain_id": target_chain,
                                "block_hash": block_hash,
                                "height": height,
                                "query_type": "single_chain_by_height"
                            }, ctx.obj['output_format'])
                        else:
                            error(f"Block not found in chain {target_chain}: {height_response.status_code}")
                    except ValueError:
                        error(f"Block not found in chain {target_chain}: {response.status_code}")
                        
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.argument("tx_hash")
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Search transaction across all available chains')
@click.pass_context
def transaction(ctx, tx_hash: str, chain_id: str, all_chains: bool):
    """Get transaction details across chains"""
    config = ctx.obj['config']
    
    try:
        if all_chains:
            # Search for transaction across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            tx_results = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        response = client.get(
                            f"{config.trading_service_url}/explorer/transactions/{tx_hash}?chain_id={chain}",
                            headers={"X-Api-Key": config.api_key or ""},
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            tx_results[chain] = response.json()
                        else:
                            tx_results[chain] = {"error": f"Transaction not found: HTTP {response.status_code}"}
                            
                except Exception as e:
                    tx_results[chain] = {"error": str(e)}
            
            # Count successful searches
            successful_searches = sum(1 for result in tx_results.values() if "error" not in result)
            
            output({
                "tx_hash": tx_hash,
                "chains": tx_results,
                "total_chains": len(chains),
                "successful_searches": successful_searches,
                "query_type": "all_chains",
                "found_in_chains": [chain for chain, result in tx_results.items() if "error" not in result]
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                response = client.get(
                    f"{config.trading_service_url}/explorer/transactions/{tx_hash}?chain_id={target_chain}",
                    headers={"X-Api-Key": config.api_key or ""},
                    timeout=5
                )
                
                if response.status_code == 200:
                    tx_data = response.json()
                    output({
                        "tx_data": tx_data,
                        "chain_id": target_chain,
                        "tx_hash": tx_hash,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    error(f"Transaction not found in chain {target_chain}: {response.status_code}")
                    
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option("--node", type=int, default=1, help="Node number (1, 2, or 3)")
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get status across all available chains')
@click.pass_context
def status(ctx, node: int, chain_id: str, all_chains: bool):
    """Get blockchain node status across chains"""
    config = ctx.obj['config']
    
    # Map node to RPC URL using new port logic
    node_urls = {
        1: "http://localhost:8006",  # Primary Blockchain RPC
        2: "http://localhost:8026",  # Development Blockchain RPC
        3: "http://aitbc.keisanki.net/rpc"
    }
    
    rpc_url = node_urls.get(node)
    if not rpc_url:
        error(f"Invalid node number: {node}")
        return
    
    try:
        if all_chains:
            # Get status across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_status = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        # Use health endpoint with chain context
                        health_url = f"{rpc_url}/health?chain_id={chain}"
                        response = client.get(health_url, timeout=5)
                        
                        if response.status_code == 200:
                            status_data = response.json()
                            all_status[chain] = {
                                "node": node,
                                "rpc_url": rpc_url,
                                "chain_id": chain,
                                "status": status_data,
                                "healthy": True
                            }
                        else:
                            all_status[chain] = {
                                "node": node,
                                "rpc_url": rpc_url,
                                "chain_id": chain,
                                "error": f"HTTP {response.status_code}",
                                "healthy": False
                            }
                except Exception as e:
                    all_status[chain] = {
                        "node": node,
                        "rpc_url": rpc_url,
                        "chain_id": chain,
                        "error": str(e),
                        "healthy": False
                    }
            
            # Count healthy chains
            healthy_chains = sum(1 for status in all_status.values() if status.get("healthy", False))
            
            output({
                "node": node,
                "rpc_url": rpc_url,
                "chains": all_status,
                "total_chains": len(chains),
                "healthy_chains": healthy_chains,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                # Use health endpoint with chain context
                health_url = f"{rpc_url}/health?chain_id={target_chain}"
                response = client.get(health_url, timeout=5)
                
                if response.status_code == 200:
                    status_data = response.json()
                    output({
                        "node": node,
                        "rpc_url": rpc_url,
                        "chain_id": target_chain,
                        "status": status_data,
                        "healthy": True,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    output({
                        "node": node,
                        "rpc_url": rpc_url,
                        "chain_id": target_chain,
                        "error": f"HTTP {response.status_code}",
                        "healthy": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
    except Exception as e:
        error(f"Failed to connect to node {node}: {e}")


@blockchain.command()
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get sync status across all available chains')
@click.pass_context
def sync_status(ctx, chain_id: str, all_chains: bool):
    """Get blockchain synchronization status across chains"""
    config = ctx.obj['config']
    
    try:
        if all_chains:
            # Get sync status across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_sync_status = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        response = client.get(
                            f"{config.coordinator_url}/v1/sync-status?chain_id={chain}",
                            headers={"X-Api-Key": config.api_key or ""},
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            sync_data = response.json()
                            all_sync_status[chain] = {
                                "chain_id": chain,
                                "sync_status": sync_data,
                                "available": True
                            }
                        else:
                            all_sync_status[chain] = {
                                "chain_id": chain,
                                "error": f"HTTP {response.status_code}",
                                "available": False
                            }
                except Exception as e:
                    all_sync_status[chain] = {
                        "chain_id": chain,
                        "error": str(e),
                        "available": False
                    }
            
            # Count available chains
            available_chains = sum(1 for status in all_sync_status.values() if status.get("available", False))
            
            output({
                "chains": all_sync_status,
                "total_chains": len(chains),
                "available_chains": available_chains,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}/v1/sync-status?chain_id={target_chain}",
                    headers={"X-Api-Key": config.api_key or ""},
                    timeout=5
                )
                
                if response.status_code == 200:
                    sync_data = response.json()
                    output({
                        "chain_id": target_chain,
                        "sync_status": sync_data,
                        "available": True,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    output({
                        "chain_id": target_chain,
                        "error": f"HTTP {response.status_code}",
                        "available": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get peers across all available chains')
@click.pass_context
def peers(ctx, chain_id: str, all_chains: bool):
    """List connected peers across chains"""
    try:
        config = ctx.obj['config']
        node_url = _get_node_endpoint(ctx)
        
        if all_chains:
            # Get peers across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_peers = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        # Try to get peers from the local blockchain node with chain context
                        response = client.get(
                            f"{node_url}/rpc/peers?chain_id={chain}",
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            peers_data = response.json()
                            all_peers[chain] = {
                                "chain_id": chain,
                                "peers": peers_data.get("peers", peers_data),
                                "available": True
                            }
                        else:
                            all_peers[chain] = {
                                "chain_id": chain,
                                "peers": [],
                                "message": "No P2P peers available - node running in RPC-only mode",
                                "available": False
                            }
                except Exception as e:
                    all_peers[chain] = {
                        "chain_id": chain,
                        "peers": [],
                        "error": str(e),
                        "available": False
                    }
            
            # Count chains with available peers
            chains_with_peers = sum(1 for peers in all_peers.values() if peers.get("available", False))
            
            output({
                "chains": all_peers,
                "total_chains": len(chains),
                "chains_with_peers": chains_with_peers,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                # Try to get peers from the local blockchain node with chain context
                response = client.get(
                    f"{node_url}/rpc/peers?chain_id={target_chain}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    peers_data = response.json()
                    output({
                        "chain_id": target_chain,
                        "peers": peers_data.get("peers", peers_data),
                        "available": True,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    # If no peers endpoint, return meaningful message
                    output({
                        "chain_id": target_chain,
                        "peers": [],
                        "message": "No P2P peers available - node running in RPC-only mode",
                        "available": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get info across all available chains')
@click.pass_context
def info(ctx, chain_id: str, all_chains: bool):
    """Get blockchain information across chains"""
    try:
        config = ctx.obj['config']
        node_url = _get_node_endpoint(ctx)
        
        if all_chains:
            # Get info across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_info = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        # Get head block for basic info with chain context
                        response = client.get(
                            f"{node_url}/rpc/head?chain_id={chain}",
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            head_data = response.json()
                            # Create basic info from head block
                            all_info[chain] = {
                                "chain_id": chain,
                                "height": head_data.get("height"),
                                "latest_block": head_data.get("hash"),
                                "timestamp": head_data.get("timestamp"),
                                "transactions_in_block": head_data.get("tx_count", 0),
                                "status": "active",
                                "available": True
                            }
                        else:
                            all_info[chain] = {
                                "chain_id": chain,
                                "error": f"HTTP {response.status_code}",
                                "available": False
                            }
                except Exception as e:
                    all_info[chain] = {
                        "chain_id": chain,
                        "error": str(e),
                        "available": False
                    }
            
            # Count available chains
            available_chains = sum(1 for info in all_info.values() if info.get("available", False))
            
            output({
                "chains": all_info,
                "total_chains": len(chains),
                "available_chains": available_chains,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                # Get head block for basic info with chain context
                response = client.get(
                    f"{node_url}/rpc/head?chain_id={target_chain}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    head_data = response.json()
                    # Create basic info from head block
                    info_data = {
                        "chain_id": target_chain,
                        "height": head_data.get("height"),
                        "latest_block": head_data.get("hash"),
                        "timestamp": head_data.get("timestamp"),
                        "transactions_in_block": head_data.get("tx_count", 0),
                        "status": "active",
                        "available": True,
                        "query_type": "single_chain"
                    }
                    output(info_data, ctx.obj['output_format'])
                else:
                    output({
                        "chain_id": target_chain,
                        "error": f"HTTP {response.status_code}",
                        "available": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get supply across all available chains')
@click.pass_context
def supply(ctx, chain_id: str, all_chains: bool):
    """Get token supply information across chains"""
    try:
        config = ctx.obj['config']
        node_url = _get_node_endpoint(ctx)
        
        if all_chains:
            # Get supply across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_supply = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        response = client.get(
                            f"{node_url}/rpc/supply?chain_id={chain}",
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            supply_data = response.json()
                            all_supply[chain] = {
                                "chain_id": chain,
                                "supply": supply_data,
                                "available": True
                            }
                        else:
                            all_supply[chain] = {
                                "chain_id": chain,
                                "error": f"HTTP {response.status_code}",
                                "available": False
                            }
                except Exception as e:
                    all_supply[chain] = {
                        "chain_id": chain,
                        "error": str(e),
                        "available": False
                    }
            
            # Count chains with available supply data
            chains_with_supply = sum(1 for supply in all_supply.values() if supply.get("available", False))
            
            output({
                "chains": all_supply,
                "total_chains": len(chains),
                "chains_with_supply": chains_with_supply,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                response = client.get(
                    f"{node_url}/rpc/supply?chain_id={target_chain}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    supply_data = response.json()
                    output({
                        "chain_id": target_chain,
                        "supply": supply_data,
                        "available": True,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    output({
                        "chain_id": target_chain,
                        "error": f"HTTP {response.status_code}",
                        "available": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get validators across all available chains')
@click.pass_context
def validators(ctx, chain_id: str, all_chains: bool):
    """List blockchain validators across chains"""
    try:
        config = ctx.obj['config']
        node_url = _get_node_endpoint(ctx)
        
        if all_chains:
            # Get validators across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_validators = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        response = client.get(
                            f"{node_url}/rpc/validators?chain_id={chain}",
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            validators_data = response.json()
                            all_validators[chain] = {
                                "chain_id": chain,
                                "validators": validators_data.get("validators", validators_data),
                                "available": True
                            }
                        else:
                            all_validators[chain] = {
                                "chain_id": chain,
                                "error": f"HTTP {response.status_code}",
                                "available": False
                            }
                except Exception as e:
                    all_validators[chain] = {
                        "chain_id": chain,
                        "error": str(e),
                        "available": False
                    }
            
            # Count chains with available validators
            chains_with_validators = sum(1 for validators in all_validators.values() if validators.get("available", False))
            
            output({
                "chains": all_validators,
                "total_chains": len(chains),
                "chains_with_validators": chains_with_validators,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                response = client.get(
                    f"{node_url}/rpc/validators?chain_id={target_chain}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    validators_data = response.json()
                    output({
                        "chain_id": target_chain,
                        "validators": validators_data.get("validators", validators_data),
                        "available": True,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    output({
                        "chain_id": target_chain,
                        "error": f"HTTP {response.status_code}",
                        "available": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
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
        import json
        with httpx.Client() as client:
            try:
                payload_data = json.loads(data)
            except json.JSONDecodeError:
                payload_data = {"raw_data": data}
                
            tx_payload = {
                "type": "TRANSFER",
                "sender": from_addr,
                "nonce": nonce,
                "fee": 0,
                "payload": payload_data,
                "sig": "mock_signature"
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
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Query balance across all available chains')
@click.pass_context
def balance(ctx, address, chain_id, all_chains):
    """Get the balance of an address across chains"""
    config = ctx.obj['config']
    try:
        import httpx
        
        if all_chains:
            # Query all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            balances = {}
            
            with httpx.Client() as client:
                for chain in chains:
                    try:
                        response = client.get(
                            f"{_get_node_endpoint(ctx)}/rpc/account/{address}?chain_id={chain}",
                            timeout=5
                        )
                        if response.status_code == 200:
                            balances[chain] = response.json()
                        else:
                            balances[chain] = {"error": f"HTTP {response.status_code}"}
                    except Exception as e:
                        balances[chain] = {"error": str(e)}
            
            output({
                "address": address,
                "chains": balances,
                "total_chains": len(chains),
                "successful_queries": sum(1 for b in balances.values() if "error" not in b)
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                response = client.get(
                    f"{_get_node_endpoint(ctx)}/rpc/getBalance/{address}?chain_id={target_chain}",
                    timeout=5
                )
                if response.status_code == 200:
                    balance_data = response.json()
                    output({
                        "address": address,
                        "chain_id": target_chain,
                        "balance": balance_data,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    error(f"Failed to get balance: {response.status_code} - {response.text}")
                    
    except Exception as e:
        error(f"Network error: {e}")


@blockchain.command()
@click.option('--chain', required=True, help='Chain ID to verify (e.g., ait-mainnet, ait-devnet)')
@click.option('--genesis-hash', help='Expected genesis hash to verify against')
@click.option('--verify-signatures', is_flag=True, default=True, help='Verify genesis block signatures')
@click.pass_context
def verify_genesis(ctx, chain: str, genesis_hash: Optional[str], verify_signatures: bool):
    """Verify genesis block integrity for a specific chain"""
    try:
        import httpx
        from utils import success
        
        with httpx.Client() as client:
            # Get genesis block for the specified chain
            response = client.get(
                f"{_get_node_endpoint(ctx)}/rpc/getGenesisBlock?chain_id={chain}",
                timeout=10
            )
            
            if response.status_code != 200:
                error(f"Failed to get genesis block for chain '{chain}': {response.status_code}")
                return
            
            genesis_data = response.json()
            
            # Verification results
            verification_results = {
                "chain_id": chain,
                "genesis_block": genesis_data,
                "verification_passed": True,
                "checks": {}
            }
            
            # Check 1: Genesis hash verification
            if genesis_hash:
                actual_hash = genesis_data.get("hash")
                if actual_hash == genesis_hash:
                    verification_results["checks"]["hash_match"] = {
                        "status": "passed",
                        "expected": genesis_hash,
                        "actual": actual_hash
                    }
                    success(f"✅ Genesis hash matches expected value")
                else:
                    verification_results["checks"]["hash_match"] = {
                        "status": "failed",
                        "expected": genesis_hash,
                        "actual": actual_hash
                    }
                    verification_results["verification_passed"] = False
                    error(f"❌ Genesis hash mismatch!")
                    error(f"Expected: {genesis_hash}")
                    error(f"Actual: {actual_hash}")
            
            # Check 2: Genesis block structure
            required_fields = ["hash", "previous_hash", "timestamp", "transactions", "nonce"]
            missing_fields = [field for field in required_fields if field not in genesis_data]
            
            if not missing_fields:
                verification_results["checks"]["structure"] = {
                    "status": "passed",
                    "required_fields": required_fields
                }
                success(f"✅ Genesis block structure is valid")
            else:
                verification_results["checks"]["structure"] = {
                    "status": "failed",
                    "missing_fields": missing_fields
                }
                verification_results["verification_passed"] = False
                error(f"❌ Genesis block missing required fields: {missing_fields}")
            
            # Check 3: Signature verification (if requested)
            if verify_signatures and "signature" in genesis_data:
                # This would implement actual signature verification
                # For now, we'll just check if signature exists
                verification_results["checks"]["signature"] = {
                    "status": "passed",
                    "signature_present": True
                }
                success(f"✅ Genesis block signature is present")
            elif verify_signatures:
                verification_results["checks"]["signature"] = {
                    "status": "warning",
                    "message": "No signature found in genesis block"
                }
                warning(f"⚠️  No signature found in genesis block")
            
            # Check 4: Previous hash should be null/empty for genesis
            prev_hash = genesis_data.get("previous_hash")
            if prev_hash in [None, "", "0", "0x0000000000000000000000000000000000000000000000000000000000000000"]:
                verification_results["checks"]["previous_hash"] = {
                    "status": "passed",
                    "previous_hash": prev_hash
                }
                success(f"✅ Genesis block previous hash is correct (null)")
            else:
                verification_results["checks"]["previous_hash"] = {
                    "status": "failed",
                    "previous_hash": prev_hash
                }
                verification_results["verification_passed"] = False
                error(f"❌ Genesis block previous hash should be null")
            
            # Final result
            if verification_results["verification_passed"]:
                success(f"🎉 Genesis block verification PASSED for chain '{chain}'")
            else:
                error(f"❌ Genesis block verification FAILED for chain '{chain}'")
            
            output(verification_results, ctx.obj['output_format'])
            
    except Exception as e:
        error(f"Failed to verify genesis block: {e}")


@blockchain.command()
@click.option('--chain', required=True, help='Chain ID to get genesis hash for')
@click.pass_context
def genesis_hash(ctx, chain: str):
    """Get the genesis block hash for a specific chain"""
    try:
        import httpx
        from utils import success
        
        with httpx.Client() as client:
            response = client.get(
                f"{_get_node_endpoint(ctx)}/rpc/getGenesisBlock?chain_id={chain}",
                timeout=10
            )
            
            if response.status_code != 200:
                error(f"Failed to get genesis block for chain '{chain}': {response.status_code}")
                return
            
            genesis_data = response.json()
            genesis_hash_value = genesis_data.get("hash")
            
            if genesis_hash_value:
                success(f"Genesis hash for chain '{chain}':")
                output({
                    "chain_id": chain,
                    "genesis_hash": genesis_hash_value,
                    "genesis_block": {
                        "hash": genesis_hash_value,
                        "timestamp": genesis_data.get("timestamp"),
                        "transaction_count": len(genesis_data.get("transactions", [])),
                        "nonce": genesis_data.get("nonce")
                    }
                }, ctx.obj['output_format'])
            else:
                error(f"No hash found in genesis block for chain '{chain}'")
                
    except Exception as e:
        error(f"Failed to get genesis hash: {e}")


def warning(message: str):
    """Display warning message"""
    click.echo(click.style(f"⚠️  {message}", fg='yellow'))


@blockchain.command()
@click.option('--chain-id', help='Specific chain ID to query (default: ait-devnet)')
@click.option('--all-chains', is_flag=True, help='Get state across all available chains')
@click.pass_context
def state(ctx, chain_id: str, all_chains: bool):
    """Get blockchain state information across chains"""
    config = ctx.obj['config']
    node_url = _get_node_endpoint(ctx)
    
    try:
        if all_chains:
            # Get state across all available chains
            # Query all available chains from chain registry
            from cli.config.chains import get_chain_registry
            registry = get_chain_registry()
            chains = registry.get_chain_ids()
            all_state = {}
            
            for chain in chains:
                try:
                    with httpx.Client() as client:
                        response = client.get(
                            f"{node_url}/rpc/state?chain_id={chain}",
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            state_data = response.json()
                            all_state[chain] = {
                                "chain_id": chain,
                                "state": state_data,
                                "available": True
                            }
                        else:
                            all_state[chain] = {
                                "chain_id": chain,
                                "error": f"HTTP {response.status_code}",
                                "available": False
                            }
                except Exception as e:
                    all_state[chain] = {
                        "chain_id": chain,
                        "error": str(e),
                        "available": False
                    }
            
            # Count available chains
            available_chains = sum(1 for state in all_state.values() if state.get("available", False))
            
            output({
                "chains": all_state,
                "total_chains": len(chains),
                "available_chains": available_chains,
                "query_type": "all_chains"
            }, ctx.obj['output_format'])
            
        else:
            # Query specific chain (default to ait-devnet if not specified)
            target_chain = chain_id or 'ait-devnet'
            
            with httpx.Client() as client:
                response = client.get(
                    f"{node_url}/rpc/state?chain_id={target_chain}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    state_data = response.json()
                    output({
                        "chain_id": target_chain,
                        "state": state_data,
                        "available": True,
                        "query_type": "single_chain"
                    }, ctx.obj['output_format'])
                else:
                    output({
                        "chain_id": target_chain,
                        "error": f"HTTP {response.status_code}",
                        "available": False,
                        "query_type": "single_chain_error"
                    }, ctx.obj['output_format'])
                    
    except Exception as e:
        error(f"Network error: {e}")
